from datetime import date, datetime, time, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client

from app import codes
from app.auth import get_current_student_id
from app.db import get_db_client
from app.lifecycle import GroupLifecycle, GroupStatus, check_in_allowed
from app.repositories import (
    CheckInConflictError,
    InvitationConflictError,
    RecordNotFoundError,
    RepositoryError,
)
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository
from app.timezones import APPLICATION_TIMEZONE

router = APIRouter(prefix="/groups", tags=["groups"])

GroupResponse = Literal["pending", "joined", "skipped"]
GroupLifecycleStatus = Literal[
    "forming",
    "confirmed",
    "active",
    "completed",
    "dissolved",
]


class MeetingSpot(BaseModel):
    building: str
    walk_min: int = Field(ge=0, description="Approximate walking time in minutes")


class SuggestedGroup(BaseModel):
    id: str = Field(description="Opaque group identifier")
    members: list[str] = Field(description="First names visible to the suggested student")
    shared: list[str] = Field(description="Short explanations for why the group matches")
    spot: MeetingSpot
    response: GroupResponse
    status: GroupLifecycleStatus = Field(description="Current group lifecycle state")
    accepted_count: int = Field(ge=0, description="Accepted invitation count")
    minimum_required: int = Field(
        default=3,
        ge=3,
        le=3,
        description="Acceptances required to confirm the group",
    )
    invite_expires_at: datetime = Field(
        description="Absolute deadline for accepting or declining this invitation"
    )


class GroupResponseUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"group_id": "g_41", "response": "joined"}}
    )

    group_id: str
    response: Literal["joined", "skipped"]


class CheckInCodeOut(BaseModel):
    code: str = Field(description="Short-lived signed hc1 member code")
    expires_in: int = Field(
        ge=1,
        le=codes.CHECKIN_WINDOW_SECONDS,
        description="Seconds until the displayed code rotates",
    )
    joined_count: int = Field(ge=0)
    checked_in_count: int = Field(ge=0)
    my_state: Literal["joined", "checked_in"]


class CheckInRequest(BaseModel):
    code: str = Field(min_length=1, max_length=200)


class CheckInResult(BaseModel):
    joined_count: int = Field(ge=0)
    checked_in_count: int = Field(ge=0)
    my_state: Literal["checked_in"]
    counted: bool = Field(
        description="Whether this scan recorded at least one new attendance timestamp"
    )


@router.post(
    "/{id}/join",
    response_model=GroupResponseUpdate,
    summary="Join a suggested group",
    description="Persists a joined response for the authenticated student.",
)
def join_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _update_response(client, id, student_id, "joined")


@router.post(
    "/{id}/skip",
    response_model=GroupResponseUpdate,
    summary="Skip a suggested group",
    description="Persists a skipped response for the authenticated student.",
)
def skip_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _update_response(client, id, student_id, "skipped")


def _update_response(
    client: Client,
    group_id: str,
    student_id: str,
    response: Literal["joined", "skipped"],
) -> GroupResponseUpdate:
    try:
        GroupMemberRepository(client).respond_to_invitation(
            group_id,
            student_id,
            response,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvitationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update group membership",
        ) from exc
    return GroupResponseUpdate(group_id=group_id, response=response)


def get_checkin_now() -> datetime:
    """Clock dependency kept injectable for deterministic boundary tests."""
    return datetime.now(timezone.utc)


@router.get(
    "/{id}/checkin-code",
    response_model=CheckInCodeOut,
    summary="Get the current member check-in code",
    description=(
        "Returns an hc1 code that rotates every 30 seconds. Only an accepted "
        "member of a confirmed or active group may request it during the meeting."
    ),
)
def get_checkin_code(
    id: Annotated[str, Path(description="Opaque group identifier")],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
    now: Annotated[datetime, Depends(get_checkin_now)],
) -> CheckInCodeOut:
    members, _ = _checkin_context(client, id, student_id, now)
    try:
        issued = codes.issue(student_id, now=now.timestamp())
    except codes.CheckInCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meetup check-in is not configured",
        ) from exc
    mine = next(
        member for member in members if str(member.get("student_id")) == student_id
    )
    accepted_members = [
        member for member in members if member.get("invitation_status") == "accepted"
    ]
    return CheckInCodeOut(
        code=issued.code,
        expires_in=issued.expires_in,
        joined_count=len(accepted_members),
        checked_in_count=sum(
            member.get("arrived_at") is not None for member in accepted_members
        ),
        my_state=("checked_in" if mine.get("arrived_at") is not None else "joined"),
    )


@router.post(
    "/{id}/checkin",
    response_model=CheckInResult,
    summary="Check in with another accepted group member",
    description=(
        "Validates a groupmate's short-lived hc1 code and atomically records "
        "attendance for both members. Repeated scans are idempotent."
    ),
)
def check_in_group(
    id: Annotated[str, Path(description="Opaque group identifier")],
    body: CheckInRequest,
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
    now: Annotated[datetime, Depends(get_checkin_now)],
) -> CheckInResult:
    all_members, _ = _checkin_context(client, id, student_id, now)
    try:
        presenter_id = codes.read(body.code, now=now.timestamp())
    except codes.CheckInCodeConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Meetup check-in is not configured",
        ) from exc
    if presenter_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That check-in code is invalid or expired",
        )
    if presenter_id == student_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Use a different accepted group member's code",
        )
    presenter = next(
        (
            member
            for member in all_members
            if str(member.get("student_id")) == presenter_id
        ),
        None,
    )
    if presenter is None:
        # Deliberately do not reveal whether a valid code belongs to another group.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That check-in code is invalid or expired",
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
            presenter_id,
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
    try:
        members = GroupMemberRepository(client).list_for_group(group_id)
        mine = next(
            (
                member
                for member in members
                if str(member.get("student_id")) == student_id
            ),
            None,
        )
        if mine is None:
            raise RecordNotFoundError("Group was not found")
        group = _as_lifecycle(GroupRepository(client).get(group_id))
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load meetup check-in",
        ) from exc

    if mine.get("invitation_status") != "accepted":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accept the group invitation before checking in",
        )
    if check_in_allowed(group, at=now):
        return members, group
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
    start_time = _parse_time(row["start_time"])
    end_time = _parse_time(row["end_time"])
    invite_deadline = _parse_datetime(row["invite_expires_at"])
    confirmed_at = row.get("confirmed_at")
    return GroupLifecycle(
        status=GroupStatus(str(row["status"])),
        invitation_deadline=invite_deadline,
        meeting_start=datetime.combine(on_date, start_time, APPLICATION_TIMEZONE),
        meeting_end=datetime.combine(on_date, end_time, APPLICATION_TIMEZONE),
        confirmed_at=(
            _parse_datetime(confirmed_at) if confirmed_at is not None else None
        ),
    )


def _parse_time(value: object) -> time:
    return value if isinstance(value, time) else time.fromisoformat(str(value))


def _parse_datetime(value: object) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
        str(value).replace("Z", "+00:00")
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RepositoryError("Group timestamp is missing timezone information")
    return parsed
