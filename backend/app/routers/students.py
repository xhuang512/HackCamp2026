import logging
import os
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client

from app.auth import (
    create_guest_session,
    ensure_guest_sessions_configured,
    get_current_student_id,
)
from app.db import get_db_client
from app.matching import next_matching_dates, run_matching
from app.repositories import RecordNotFoundError, ReferenceDataError, RepositoryError
from app.repositories.free_blocks import FreeBlockRepository, resolve_preset
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository
from app.repositories.reference_data import normalize_course_codes
from app.repositories.students import StudentRepository
from app.routers.groups import MeetingSpot, SuggestedGroup

router = APIRouter(tags=["students"])
logger = logging.getLogger(__name__)


class StudentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Maya",
                "tags": ["transfer"],
                "languages": ["English", "Korean"],
                "courses": ["STAT 302"],
                "preset_schedule": "tue_thu_afternoon",
            }
        }
    )

    first_name: str = Field(min_length=1, max_length=40, description="Student's first name")
    tags: list[str] = Field(
        default_factory=list,
        description="Canonical student-type tag slugs returned by GET /options",
    )
    languages: list[str] = Field(
        default_factory=list,
        description=(
            "Canonical language codes returned by GET /options; existing language "
            "names are also accepted"
        ),
    )
    courses: list[str] = Field(
        default_factory=list,
        description="UBC-style course codes; values such as stat406 normalize to STAT 406",
    )
    preset_schedule: str = Field(
        min_length=1,
        description="Frontend-defined key for a preset schedule",
        examples=["tue_thu_afternoon"],
    )


class StudentSession(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "student_id": "s_demo_01",
                "first_name": "Maya",
                "session_token": "guest_demo_session",
                "is_guest": True,
            }
        }
    )

    student_id: str = Field(description="Opaque student identifier")
    first_name: str
    session_token: str = Field(description="Temporary guest session credential")
    is_guest: bool


class Gap(BaseModel):
    day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["13:00"])
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["15:00"])


class CurrentSuggestionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gap": {"day": "tue", "start": "13:00", "end": "15:00"},
                "group": {
                    "id": "g_41",
                    "members": ["Ji-woo", "Amir", "Rosa"],
                    "shared": ["STAT 302", "2 transfers", "Korean"],
                    "spot": {"building": "The Nest", "walk_min": 4},
                    "response": "pending",
                },
            }
        }
    )

    gap: Gap
    group: SuggestedGroup


class WaitingForMatchResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"status": "waiting"}}
    )

    status: Literal["waiting"] = Field(
        description="The student is eligible but has no current group suggestion"
    )


class NoSuggestionError(Exception):
    """Raised when an authenticated student has no current suggestion."""


@router.post(
    "/students",
    response_model=StudentSession,
    status_code=status.HTTP_201_CREATED,
    summary="Create a demo student",
    description=(
        "Persists a student and preset free blocks, then returns a signed guest session."
    ),
)
def create_student(
    student: StudentCreate,
    client: Annotated[Client, Depends(get_db_client)],
) -> StudentSession:
    ensure_guest_sessions_configured()
    try:
        blocks = resolve_preset(student.preset_schedule)
    except ReferenceDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    term = os.getenv("CURRENT_TERM")
    if student.courses and not term:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CURRENT_TERM is required to persist student courses",
        )
    try:
        course_codes = normalize_course_codes(student.courses)
    except ReferenceDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    students = StudentRepository(client)
    free_blocks = FreeBlockRepository(client)
    created: dict[str, Any] | None = None
    try:
        created = students.create(student.first_name)
        student_id = str(created["id"])
        students.add_tags(student_id, student.tags)
        students.add_languages(student_id, student.languages)
        students.add_courses(student_id, course_codes, term or "")
        free_blocks.create_for_student(student_id, blocks)
    except ReferenceDataError as exc:
        _rollback_student(students, created)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except RepositoryError as exc:
        _rollback_student(students, created)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not persist student onboarding",
        ) from exc

    for target_date in next_matching_dates({block.day for block in blocks}):
        try:
            run_matching(client, target_date, persist=True)
        except RepositoryError:
            # Onboarding has already succeeded. A later signup or the batch CLI
            # can retry this student without forcing duplicate registration.
            logger.exception(
                "Automatic matching failed after creating student %s for %s",
                student_id,
                target_date,
            )

    return StudentSession(
        student_id=student_id,
        first_name=str(created["first_name"]),
        session_token=create_guest_session(student_id),
        is_guest=True,
    )


@router.get(
    "/me/now",
    response_model=CurrentSuggestionResponse | WaitingForMatchResponse,
    summary="Get the current group suggestion",
    description=(
        "Returns the authenticated student's next persisted group suggestion. "
        "The gap interval is the group's actual meeting interval. If no suggestion "
        "exists, returns HTTP 200 with `{\"status\": \"waiting\"}`."
    ),
)
def get_current_suggestion(
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> CurrentSuggestionResponse | WaitingForMatchResponse:
    students = StudentRepository(client)
    free_blocks = FreeBlockRepository(client)
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    try:
        memberships = [
            membership
            for membership in members.list_for_student(student_id)
            if membership["response"] != "skipped"
        ]
        membership_by_group = {
            str(membership["group_id"]): membership for membership in memberships
        }
        upcoming = groups.list_upcoming(list(membership_by_group))
        group = _first_group_with_availability(
            upcoming,
            free_blocks.list_for_student(student_id),
        )
        group_id = str(group["id"])
        group_members = members.list_for_group(group_id)
        active_members = [
            member for member in group_members if member["response"] != "skipped"
        ]
        member_ids = [str(member["student_id"]) for member in active_members]
        current_response = membership_by_group[group_id]["response"]
        names: list[str] = []
        if current_response == "joined":
            names_by_id = students.public_names(member_ids)
            names = [names_by_id[item] for item in member_ids if item in names_by_id]
        shared = students.shared_signals(member_ids)
        everyone_joined = bool(group_members) and all(
            member["response"] == "joined" for member in group_members
        )
        building = (
            groups.building_name(group.get("building_id"))
            if everyone_joined
            else "To be announced"
        )
    except NoSuggestionError:
        return WaitingForMatchResponse(status="waiting")
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load the current group suggestion",
        ) from exc

    return CurrentSuggestionResponse(
        gap=Gap(
            day=_day_name(date.fromisoformat(str(group["on_date"])).weekday()),
            start=_short_time(str(group["start_time"])),
            end=_short_time(str(group["end_time"])),
        ),
        group=SuggestedGroup(
            id=group_id,
            members=names,
            shared=shared,
            spot=MeetingSpot(building=building, walk_min=0),
            response=current_response,
        ),
    )


def _rollback_student(
    repository: StudentRepository,
    created: dict[str, Any] | None,
) -> None:
    if created is None or "id" not in created:
        return
    try:
        repository.delete(str(created["id"]))
    except RepositoryError:
        # Preserve the original database error. The service-role logs retain its
        # chained cause without exposing database details to the client.
        pass


def _first_group_with_availability(
    groups: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    for group in groups:
        group_date = date.fromisoformat(str(group["on_date"]))
        group_start = _short_time(str(group["start_time"]))
        group_end = _short_time(str(group["end_time"]))
        for block in blocks:
            if (
                int(block["day"]) == group_date.weekday()
                and _short_time(str(block["start_time"])) <= group_start
                and _short_time(str(block["end_time"])) >= group_end
            ):
                return group
    raise NoSuggestionError


def _short_time(value: str) -> str:
    return value[:5]


def _day_name(day: int) -> Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
    names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    if not 0 <= day < len(names):
        raise RepositoryError("Database returned an invalid free-block day")
    return names[day]
