"""Groups: join, skip, start one, look at yours, check in.

The join and skip routes are the ones that came over with the merged
backend. Their paths and their response bodies are unchanged, because the
frontend and the tests both already speak them. Everything below them is new
and follows the API contract in docs/AGENTS.md.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict
from supabase import Client

from app import codes, store
from app.auth import get_current_student_id, onboarded_user
from app.constants import (
    CONFIRMED,
    FORMING,
    MAX_GROUP_SIZE,
)
from app.db import get_db_client
from app.groups_view import (
    checked_in_members,
    gap_of,
    group_out,
    joined_members,
    live_members,
    state_for,
)
from app.lifecycle import GroupLifecycle, GroupStatus, check_in_allowed
from app.models import (
    CheckInCodeOut,
    CheckInRequest,
    CheckInResult,
    CreateGroupRequest,
    GroupOut,
    OpenGroupOut,
)
from app.repositories import (
    CheckInConflictError,
    InvitationConflictError,
    RecordNotFoundError,
    RepositoryError,
)
from app.repositories.buildings import BuildingRepository
from app.repositories.free_blocks import FreeBlockRepository
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import INVITATION_LEAD, GroupRepository
from app.repositories.students import StudentRepository
from app.timezones import APPLICATION_TIMEZONE

router = APIRouter(prefix="/groups", tags=["groups"])

# How long an "I'm free now" group runs when the student has no free block
# covering this moment. Long enough to meet somebody, short enough that it
# expires on its own during a demo.
DEFAULT_NOW_MINUTES = 120

# An "I'm free now" group starts this many minutes from now, and its
# invitations stay open until it starts. That is the window other students
# have to find it in GET /groups/open and join before the meeting begins.
# A group cannot start at this exact minute: its invitation deadline would
# already have passed, which both the repository and the database refuse.
NOW_LEAD_MINUTES = 5

# Shown instead of the building for a group that is still forming. The spot
# is revealed only once three people have joined.
FORMING_AREA = "Location shared once 3 people join"


class GroupResponseUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"group_id": "g_41", "response": "joined"}}
    )

    group_id: str
    # Compatibility wire values. Durable storage uses accepted/declined.
    response: Literal["joined", "skipped"]


# ---------------------------------------------------------------- responding


@router.post(
    "/{id}/join",
    response_model=GroupResponseUpdate,
    summary="Join a suggested or open group",
)
def join_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student: Annotated[store.Student, Depends(onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _respond(client, id, student, "joined")


@router.post(
    "/{id}/skip",
    response_model=GroupResponseUpdate,
    summary="Decline a suggested group",
)
def skip_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student: Annotated[store.Student, Depends(onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _respond(client, id, student, "skipped")


def _respond(
    client: Client,
    group_id: str,
    student: store.Student,
    response: Literal["joined", "skipped"],
) -> GroupResponseUpdate:
    members = GroupMemberRepository(client)
    try:
        members.respond_to_invitation(
            group_id,
            student.id,
            response,
        )
    except RecordNotFoundError as exc:
        # A suggested group already has an invited membership to update. An
        # open group deliberately does not: joining it creates the membership
        # after re-checking every rule that made it open in the first place.
        if response == "joined":
            try:
                group = GroupRepository(client).get(group_id)
                group_members = members.list_for_group(group_id)
                # Not open, or not in the caller's gap, means the caller has
                # no relationship to this group at all. Saying why would
                # confirm it exists, so both fall through to the 404 below.
                # "Full" is different: GET /groups/open already showed this
                # group to the caller, so the only new fact is that it filled
                # up while they were deciding, which is worth telling them.
                state = state_for(group, group_members)
                if not _overlaps_a_gap(group, student):
                    raise RecordNotFoundError(str(exc))
                if state == CONFIRMED:
                    if len(joined_members(group_members)) >= MAX_GROUP_SIZE:
                        raise HTTPException(status_code=409, detail="That group is full.")
                    members.create_joined(group_id, student.id)
                    return GroupResponseUpdate(group_id=group_id, response=response)
                if state == FORMING and _forming_and_open(group, group_members):
                    if len(live_members(group_members)) >= MAX_GROUP_SIZE:
                        raise HTTPException(status_code=409, detail="That group is full.")
                    _join_forming(members, group_id, student.id)
                    return GroupResponseUpdate(group_id=group_id, response=response)
                raise RecordNotFoundError(str(exc))
            except HTTPException:
                raise
            except InvitationConflictError as conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(conflict)
                ) from conflict
            except RecordNotFoundError:
                pass
            except RepositoryError as create_exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Could not join the open group",
                ) from create_exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvitationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update group membership",
        ) from exc
    return GroupResponseUpdate(group_id=group_id, response=response)


def _forming_and_open(group: dict, group_members: list[dict]) -> bool:
    """Can a student who was not invited join this forming group?

    Only while its invitations are still open, and only when nobody is still
    waiting on an invitation to it. That covers a group a student started
    (the founder is its only member) and a matched group whose invitations
    have all been answered, without letting a stranger take a seat that the
    matcher is holding for somebody it invited.
    """
    deadline = datetime.fromisoformat(
        str(group["invite_expires_at"]).replace("Z", "+00:00")
    )
    if datetime.now(timezone.utc) >= deadline:
        return False
    return not any(
        member.get("invitation_status") == "invited" for member in group_members
    )


def _join_forming(members: GroupMemberRepository, group_id: str, student_id: str) -> None:
    """Join a forming group through the same atomic path an invitee uses.

    The membership is created as an invitation and accepted by the
    respond_to_group_invitation RPC, which locks the group, re-checks its
    status and deadline, and confirms it on the third acceptance in one
    transaction. Inserting an accepted row directly would skip all three.
    If the RPC refuses, the invitation row is removed again.
    """
    members.create_invited(group_id, (student_id,))
    try:
        members.respond_to_invitation(group_id, student_id, "joined")
    except Exception:
        try:
            members.remove(group_id, student_id)
        except RepositoryError:
            pass
        raise


# ------------------------------------------------------------- open groups


@router.get(
    "/open",
    response_model=list[OpenGroupOut],
    summary="Groups in the caller's gaps that the caller can still join",
    description=(
        "No names and no exact spot. A student who has not joined sees the "
        "time, the general area and what the group shares."
    ),
)
def list_open_groups(
    student: Annotated[store.Student, Depends(onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> list[OpenGroupOut]:
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)
    students = StudentRepository(client)

    try:
        mine = {
            str(membership["group_id"])
            for membership in members.list_for_student(student.id)
        }
        candidates = [
            group
            for group in groups.list_from(date.today())
            if str(group["id"]) not in mine
        ]
        memberships = members.list_for_groups([str(g["id"]) for g in candidates])
        by_group: dict[str, list[dict]] = {}
        for membership in memberships:
            by_group.setdefault(str(membership["group_id"]), []).append(membership)

        out: list[OpenGroupOut] = []
        for group in candidates:
            group_members = by_group.get(str(group["id"]), [])
            state = state_for(group, group_members)
            if state == CONFIRMED:
                seats_left = MAX_GROUP_SIZE - len(joined_members(group_members))
                # The general area, which for a confirmed group with seats
                # left is the building name. AGENTS.md allows it before
                # joining; what stays hidden is who is there.
                area = groups.building_name(group.get("building_id"))
            elif state == FORMING and _forming_and_open(group, group_members):
                # Pending invitations would hold seats too, but an open
                # forming group has none, so live members are the count.
                seats_left = MAX_GROUP_SIZE - len(live_members(group_members))
                # The spot stays hidden while a group is forming.
                area = FORMING_AREA
            else:
                continue
            if seats_left <= 0:
                continue
            if not _overlaps_a_gap(group, student):
                continue
            out.append(
                OpenGroupOut(
                    id=str(group["id"]),
                    gap=gap_of(group),
                    mode=str(group.get("mode") or "social"),
                    area=area,
                    seats_left=seats_left,
                    shared=students.shared_signals(
                        [str(m["student_id"]) for m in live_members(group_members)]
                    ),
                )
            )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load open groups",
        ) from exc
    return out


def _overlaps_a_gap(group: dict, student: store.Student) -> bool:
    """Does this group sit inside one of the student's free blocks?

    AGENTS.md lists open groups "in the student's gap", so a group during a
    lecture is not an option however many seats it has.
    """
    on_date = date.fromisoformat(str(group["on_date"]))
    start = time.fromisoformat(str(group["start_time"]))
    end = time.fromisoformat(str(group["end_time"]))
    return any(
        day == on_date.weekday() and block_start < end and block_end > start
        for day, block_start, block_end in student.free_blocks
    )


# ------------------------------------------------------------ start a group


@router.post(
    "",
    response_model=GroupOut,
    status_code=201,
    summary="Start a group for a gap at a chosen building",
    description=(
        "'I'm free now' or 'Start a group for my gap'. The caller is the "
        "first joined member and picks the spot, so it is visible from the "
        "start. The matcher fills the group like any other."
    ),
)
def create_group(
    body: CreateGroupRequest,
    student: Annotated[store.Student, Depends(onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupOut:
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    try:
        building = BuildingRepository(client).by_slug(body.building)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not read buildings",
        ) from exc

    on_date, start, end, lead = _slot_for(student, now=body.now)

    created = None
    try:
        created = groups.create(
            on_date=on_date,
            start_time=start,
            end_time=end,
            building_id=int(building["id"]),
            mode=body.mode,
            invitation_lead=lead,
        )
        group_id = str(created["id"])
        members.create_joined(group_id, student.id)
    except RepositoryError as exc:
        if created is not None and "id" in created:
            try:
                groups.delete(str(created["id"]))
            except RepositoryError:
                pass
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not start the group",
        ) from exc

    return group_out(client, groups.get(group_id), student.id)


def _slot_for(
    student: store.Student, *, now: bool
) -> tuple[date, time, time, timedelta]:
    """When the group meets, and how long before that its invitations close.

    "I'm free now" starts NOW_LEAD_MINUTES from now and takes answers right
    up to its start, so other students have that window to join. It runs to
    the end of the free block covering its start, or DEFAULT_NOW_MINUTES
    when the student is not supposed to be free at all. Someone whose class
    was cancelled is not lying about being free, so this does not refuse
    them.

    Everything is Vancouver wall-clock time, the same clock the repository
    and the database use for the invitation deadline.
    """
    moment = datetime.now(APPLICATION_TIMEZONE)
    if now:
        begins = (moment + timedelta(minutes=NOW_LEAD_MINUTES + 1)).replace(
            second=0, microsecond=0
        )
        on_date = begins.date()
        start = begins.time().replace(tzinfo=None)
        covering = [
            block_end
            for day, block_start, block_end in student.free_blocks
            if day == on_date.weekday() and block_start <= start < block_end
        ]
        if covering:
            end = max(covering)
        else:
            finish = begins + timedelta(minutes=DEFAULT_NOW_MINUTES)
            end = (
                finish.time().replace(tzinfo=None)
                if finish.date() == on_date
                else time(23, 59)
            )
        if end <= start:
            raise HTTPException(
                status_code=422,
                detail="It is too late today to start a group now.",
            )
        return on_date, start, end, timedelta(0)

    if not student.free_blocks:
        raise HTTPException(
            status_code=422,
            detail="Add a schedule before starting a group for a gap.",
        )

    today = moment.weekday()
    # A gap whose invitations would already be closed is next week's.
    cutoff = (moment + INVITATION_LEAD).time().replace(tzinfo=None)

    def days_until(block: tuple[int, time, time]) -> int:
        day, start, _end = block
        days = (day - today) % 7
        return 7 if days == 0 and start <= cutoff else days

    day, start, end = min(
        student.free_blocks, key=lambda block: (days_until(block), block[1])
    )
    return (
        moment.date() + timedelta(days=days_until((day, start, end))),
        start,
        end,
        INVITATION_LEAD,
    )


@router.get(
    "/{id}",
    response_model=GroupOut,
    summary="A group, for its members only",
)
def get_group(
    id: Annotated[str, Path(description="Opaque group identifier")],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupOut:
    members, group = _member_and_group(client, id, student_id)
    return group_out(client, group, student_id, members=members)


def _member_and_group(client: Client, group_id: str, student_id: str):
    """Load a group the caller is actually in, or 404.

    404 and not 403, because a caller who is not in the group should not learn
    whether it exists.
    """
    try:
        all_members = GroupMemberRepository(client).list_for_group(group_id)
        if not any(str(m["student_id"]) == student_id for m in all_members):
            raise RecordNotFoundError("That group does not exist")
        return all_members, GroupRepository(client).get(group_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load the group",
        ) from exc


# ---------------------------------------------------------------- check in


def get_checkin_now() -> datetime:
    """Clock dependency kept injectable for deterministic boundary tests."""
    return datetime.now(timezone.utc)


@router.get(
    "/{id}/checkin-code",
    response_model=CheckInCodeOut,
    summary="The caller's current check-in code",
    description=(
        "Signed, rotates every 30 seconds, and is available only to an "
        "accepted member during a confirmed or active meeting."
    ),
)
def get_checkin_code(
    id: Annotated[str, Path(description="Opaque group identifier")],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
    now: Annotated[datetime, Depends(get_checkin_now)],
) -> CheckInCodeOut:
    all_members, _ = _checkin_context(client, id, student_id, now)
    mine = next(m for m in all_members if str(m["student_id"]) == student_id)
    joined = joined_members(all_members)
    try:
        issued = codes.issue(student_id, now=now.timestamp())
    except codes.CheckInCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meetup check-in is not configured",
        ) from exc
    return CheckInCodeOut(
        code=issued.code,
        expires_in=issued.expires_in,
        joined_count=len(joined),
        checked_in_count=len(checked_in_members(all_members)),
        my_state="checked_in" if mine.get("arrived_at") is not None else "joined",
    )


@router.post(
    "/{id}/checkin",
    response_model=CheckInResult,
    summary="Submit a scanned groupmate's code",
    description=(
        "Checks two accepted members in atomically during their meeting. "
        "Repeat scans are idempotent and cross-group codes are rejected."
    ),
)
def post_checkin(
    id: Annotated[str, Path(description="Opaque group identifier")],
    body: CheckInRequest,
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
    now: Annotated[datetime, Depends(get_checkin_now)],
) -> CheckInResult:
    all_members, _ = _checkin_context(client, id, student_id, now)

    try:
        scanned_id = codes.read(body.code, now=now.timestamp())
    except codes.CheckInCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meetup check-in is not configured",
        ) from exc
    # One answer for every bad code: wrong shape, bad signature, expired
    # window, or a member of another group. Telling a scanner which would
    # help nobody but a forger.
    if scanned_id is None:
        raise HTTPException(status_code=422, detail="That code is not valid.")
    if scanned_id == student_id:
        raise HTTPException(
            status_code=422,
            detail="Use a groupmate's code, not your own.",
        )
    if not any(str(m["student_id"]) == scanned_id for m in all_members):
        raise HTTPException(status_code=422, detail="That code is not valid.")
    presenter = next(
        m for m in all_members if str(m["student_id"]) == scanned_id
    )
    if presenter.get("invitation_status") != "accepted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Both students must accept the invitation before checking in",
        )

    try:
        result = GroupMemberRepository(client).check_in_pair(
            id,
            student_id,
            scanned_id,
            now.isoformat(),
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CheckInConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not record meetup check-in",
        ) from exc

    return CheckInResult(
        joined_count=int(result["joined_count"]),
        checked_in_count=int(result["checked_in_count"]),
        my_state="checked_in",
        counted=int(result["changed_count"]) > 0,
    )


def _checkin_context(
    client: Client,
    group_id: str,
    student_id: str,
    now: datetime,
) -> tuple[list[dict], GroupLifecycle]:
    all_members, group_row = _member_and_group(client, group_id, student_id)
    mine = next(m for m in all_members if str(m["student_id"]) == student_id)
    if mine.get("invitation_status") != "accepted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accept the group invitation before checking in",
        )

    group = _as_lifecycle(group_row)
    if check_in_allowed(group, at=now):
        return all_members, group
    if group.status == GroupStatus.FORMING:
        detail = "The group must be confirmed before check-in"
    elif group.status in {GroupStatus.COMPLETED, GroupStatus.DISSOLVED}:
        detail = "This group is no longer eligible for check-in"
    elif now < group.meeting_start:
        detail = "Check-in opens when the meeting starts"
    else:
        detail = "The meeting check-in window has ended"
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _as_lifecycle(row: dict) -> GroupLifecycle:
    on_date = row["on_date"]
    if not isinstance(on_date, date):
        on_date = date.fromisoformat(str(on_date))
    start_time = _parse_group_time(row["start_time"])
    end_time = _parse_group_time(row["end_time"])
    confirmed_at = row.get("confirmed_at")
    return GroupLifecycle(
        status=GroupStatus(str(row["status"])),
        invitation_deadline=_parse_group_datetime(row["invite_expires_at"]),
        meeting_start=datetime.combine(on_date, start_time, APPLICATION_TIMEZONE),
        meeting_end=datetime.combine(on_date, end_time, APPLICATION_TIMEZONE),
        confirmed_at=(
            _parse_group_datetime(confirmed_at) if confirmed_at is not None else None
        ),
    )


def _parse_group_time(value: object) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))


def _parse_group_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RepositoryError("Group timestamp is missing timezone information")
    return parsed
