"""Request and response shapes for signup.

These are the API contract in code. Changing a field here changes it for the
whole team, so docs/SIGNUP.md and AGENTS.md change in the same commit.
"""

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Visibility = Literal["everyone", "my_courses", "shared_tag"]

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
    group, and the hours they are free, and nothing more."""

    id: str
    first_name: str
    paused: bool
    visibility: Visibility


class MeResponse(BaseModel):
    """GET /me. The route gate's one question: is there a profile?"""

    onboarded: bool
    student: StudentOut | None = None


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
    ask_me_about: str | None = Field(default=None, max_length=120)
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
