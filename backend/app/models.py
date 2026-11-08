"""Request and response shapes for signup.

These are the API contract in code. Changing a field here changes it for the
whole team, so docs/SIGNUP.md and AGENTS.md change in the same commit.
"""

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Visibility = Literal["everyone", "my_courses", "shared_tag"]

# The five member states and five group states from AGENTS.md. checked_in is
# derived from group_members.arrived_at rather than stored as a response, so
# a checked-in member is still a joined member.
MemberState = Literal["invited", "joined", "declined", "expired", "checked_in"]
GroupState = Literal["forming", "confirmed", "active", "completed", "dissolved"]
GroupMode = Literal["social", "study"]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# At most three, per docs/SIGNUP.md's favourite spots step.
MAX_FAVOURITE_SPOTS = 3

# 0 is Monday, matching free_blocks.day in schema.sql.
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


class FreeBlockIn(BaseModel):
    """One gap between classes. What the Gemini review screen sends once a
    student has corrected what the screenshot parser read."""

    day: int = Field(ge=0, le=6)
    start: time
    end: time

    @model_validator(mode="after")
    def end_after_start(self) -> "FreeBlockIn":
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class StudentOut(BaseModel):
    """The student's own profile, to the student themselves. Nothing here is
    ever shown to anybody else: another student sees a first name inside a
    group, and the hours they are free, and nothing more.

    is_guest, tags and favourite_spots are the three fields docs/SIGNUP.md
    documents and GET /me was not sending. The Me tab needs all three: the
    guest label, the tag row, and the spots it lets a student edit.
    """

    id: str
    first_name: str
    is_guest: bool = False
    paused: bool
    visibility: Visibility
    tags: list[str] = Field(default_factory=list)
    favourite_spots: list[str] = Field(default_factory=list)


class BadgeProgress(BaseModel):
    current: int = Field(ge=0)
    target: int = Field(ge=1)


class TopBadgeOut(BaseModel):
    slug: str
    name: str


class BadgeOut(TopBadgeOut):
    earned: bool
    progress: BadgeProgress


class MeResponse(BaseModel):
    """GET /me. The route gate's one question: is there a profile?"""

    onboarded: bool
    student: StudentOut | None = None
    badges: list[BadgeOut] = Field(default_factory=list)


class GapOut(BaseModel):
    day: str
    start: str
    end: str


class AhaOut(BaseModel):
    """The one number the aha screen shows.

    free_count counts people, never names them, and excludes paused students
    because the matcher excludes them too. It is a count, so it identifies
    nobody, which is what makes it publishable at all.
    """

    gap: GapOut
    free_count: int
    same_tag_count: int
    tag: str | None


class CreateStudentRequest(BaseModel):
    """POST /students.

    There is deliberately no auth_sub field. The identity comes from the
    verified token, so this body cannot be used to create a profile for
    someone else.
    """

    first_name: str = Field(min_length=1, max_length=40)
    preset_id: str | None = None
    free_blocks: list[FreeBlockIn] | None = None
    tags: list[str] = Field(default_factory=list, max_length=10)
    languages: list[str] = Field(default_factory=list, max_length=10)
    # UBC-style course codes, normalized server side: "stat406" becomes
    # "STAT 406". The matcher's strongest shared signal, so losing these
    # costs every "you both take STAT 302" suggestion.
    courses: list[str] = Field(default_factory=list, max_length=10)
    ask_me_about: str | None = Field(default=None, max_length=120)
    # Building slugs, best first. docs/SIGNUP.md's step 4, optional, and the
    # input engine.pick_spot reads when choosing where a group meets.
    favourite_spots: list[str] = Field(
        default_factory=list, max_length=MAX_FAVOURITE_SPOTS
    )
    visibility: Visibility = "everyone"
    guest: bool = False

    @field_validator("first_name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("first_name cannot be blank")
        return trimmed

    @model_validator(mode="after")
    def one_schedule(self) -> "CreateStudentRequest":
        """A preset or explicit blocks, never both and never neither.

        Both would mean the server picks which one wins, and whichever it
        picked would be wrong half the time.
        """
        if (self.preset_id is None) == (self.free_blocks is None):
            raise ValueError("send exactly one of preset_id or free_blocks")
        if self.free_blocks is not None and not self.free_blocks:
            raise ValueError("free_blocks cannot be empty")
        return self


class CreateStudentResponse(BaseModel):
    student: StudentOut
    # None when the student has no free blocks that anybody shares. The gate
    # skips the aha screen rather than showing a zero.
    aha: AhaOut | None
    # Set only when `guest` was true and DEMO_MODE is on.
    guest_token: str | None = None


class PausedRequest(BaseModel):
    paused: bool


class PatchMeRequest(BaseModel):
    """PATCH /me. Every field optional; absent means "leave it alone".

    None is not the same as "clear it", which is why the lists default to
    None rather than []. A Me tab that sends only `paused` must not wipe the
    student's tags.
    """

    first_name: str | None = Field(default=None, min_length=1, max_length=40)
    tags: list[str] | None = Field(default=None, max_length=10)
    languages: list[str] | None = Field(default=None, max_length=10)
    ask_me_about: str | None = Field(default=None, max_length=120)
    visibility: Visibility | None = None
    favourite_spots: list[str] | None = Field(
        default=None, max_length=MAX_FAVOURITE_SPOTS
    )
    paused: bool | None = None

    @field_validator("first_name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("first_name cannot be blank")
        return trimmed


# ------------------------------------------------------------------ groups


class MeetingSpot(BaseModel):
    building: str
    walk_min: int = Field(ge=0, description="Approximate walking time in minutes")


class GroupMemberOut(BaseModel):
    first_name: str
    top_badge: TopBadgeOut | None = None


class GroupOut(BaseModel):
    """The group on the Right now card.

    `spot` is None while the group is forming, which is the privacy rule in
    code: AGENTS.md says the meeting spot is hidden until the group is
    confirmed, and a card cannot leak a building it was never sent.

    `members` carries first names and is empty unless the caller has joined
    and only names members who have joined themselves. An invitation is not
    membership, so someone who was merely invited is counted and not named.
    """

    id: str
    state: GroupState
    mode: GroupMode
    members: list[GroupMemberOut] = Field(default_factory=list)
    shared: list[str] = Field(default_factory=list)
    spot: MeetingSpot | None = None
    joined_count: int = Field(ge=0)
    checked_in_count: int = Field(ge=0)
    seats_left: int = Field(ge=0)
    my_state: MemberState
    # How many more have to join before the group confirms and the spot
    # appears. 0 once confirmed, so the card can read it straight out.
    needs: int = Field(ge=0)


class OpenGroupOut(BaseModel):
    """A confirmed group with seats left, to a student who is not in it.

    No names and no exact spot. AGENTS.md: before joining, a student sees the
    time, the general area and what they share.
    """

    id: str
    gap: "GapOut"
    mode: GroupMode
    area: str
    seats_left: int = Field(ge=0)
    shared: list[str] = Field(default_factory=list)


class NowResponse(BaseModel):
    """GET /me/now.

    `gap` is None only when the student has no free blocks at all. `group` is
    None when nothing has been suggested, and the frontend shows open groups
    instead.
    """

    gap: GapOut | None = None
    group: GroupOut | None = None


class CreateGroupRequest(BaseModel):
    """POST /groups. "I'm free now" or "Start a group for my gap".

    The student picks the building, which is the one case where the spot is
    not chosen by the matcher, so it is visible from the start.
    """

    building: str = Field(description="Building slug from GET /map")
    mode: GroupMode = "social"
    # True for "I'm free now": the group starts at this moment rather than at
    # the student's next gap.
    now: bool = False


class CheckInCodeOut(BaseModel):
    code: str
    typed: str = Field(
        description="Six-digit fallback, for a phone with no usable camera"
    )
    # ge=1, not ge=0: issue() floors the remaining seconds at one, because a
    # phone told a code expires in zero seconds has nothing useful to do.
    expires_in: int = Field(ge=1, description="Seconds until the code rotates")
    joined_count: int = Field(ge=0)
    checked_in_count: int = Field(ge=0)
    my_state: Literal["joined", "checked_in"]


class CheckInRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class CheckInResult(BaseModel):
    joined_count: int = Field(ge=0)
    checked_in_count: int = Field(ge=0)
    my_state: Literal["checked_in"]
    # False when the pair had already checked each other in. The scan
    # succeeded and changed nothing, which is what AGENTS.md asks for.
    counted: bool
    new_badges: list[TopBadgeOut] = Field(default_factory=list)


# --------------------------------------------------------------------- map


class BuildingActivity(BaseModel):
    """One building on the map. A count, never a name.

    Counts below MIN_GROUP_SIZE are not sent at all, so nobody can be singled
    out by a map pin reading "1 student".
    """

    slug: str
    name: str
    lat: float
    lng: float
    free_count: int = Field(ge=0)
    groups_meeting: int | None = Field(
        default=None,
        ge=1,
        exclude_if=lambda value: value is None,
    )


class MyGroupPin(BaseModel):
    group_id: str
    slug: str
    name: str
    lat: float
    lng: float
    joined_count: int = Field(ge=0)
    checked_in_count: int = Field(ge=0)
    state: Literal["confirmed", "active"]


class MapResponse(BaseModel):
    buildings: list[BuildingActivity]
    # Only once the group is confirmed. Forming groups have no spot to show.
    my_group: MyGroupPin | None = None


# --------------------------------------------------------------- projector


class ProjectorDot(BaseModel):
    """An anonymous cluster. No ids, no names, just a place and a size."""

    slug: str
    name: str
    lat: float
    lng: float
    count: int = Field(ge=0)


class ProjectorState(BaseModel):
    forming: int = Field(ge=0)
    confirmed: int = Field(ge=0)
    checked_in: int = Field(ge=0)
    students: int = Field(ge=0)
    dots: list[ProjectorDot] = Field(default_factory=list)
