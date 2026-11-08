"""GET /me/now: the next gap and the group suggested for it.

The lifecycle database uses invitation_status/accepted. The frontend contract
stays on the AGENTS.md GroupOut shape assembled by app/groups_view.py.
"""

import logging
from datetime import date, datetime, time, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app import store
from app.auth import onboarded_user
from app.db import get_db_client
from app.groups_view import DAY_NAMES, gap_of, group_out
from app.lifecycle_refresh import refresh_lifecycle
from app.models import GapOut, NowResponse
from app.repositories import RecordNotFoundError, RepositoryError
from app.repositories.free_blocks import FreeBlockRepository
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository
from app.timezones import APPLICATION_TIMEZONE

router = APIRouter(tags=["students"])
logger = logging.getLogger(__name__)


# POST /students lives in routers/identity.py. It owns the richer onboarding
# request and guest-token response used by the frontend route gate.


class NoSuggestionError(Exception):
    """Raised when an authenticated student has no current suggestion."""


@router.get(
    "/me/now",
    response_model=NowResponse,
    summary="The next gap and the suggested group",
    description=(
        "`group` is null when nothing has been suggested, and the frontend "
        "shows GET /groups/open instead. `spot` is null while the group is "
        "forming, because the meeting spot is hidden until the group is "
        "confirmed."
    ),
)
def get_current_suggestion(
    student: Annotated[store.Student, Depends(onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
    _lifecycle: Annotated[None, Depends(refresh_lifecycle)],
) -> NowResponse:
    free_blocks = FreeBlockRepository(client)
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    try:
        memberships = [
            membership
            for membership in members.list_for_student(student.id)
            if membership["invitation_status"] not in {"declined", "expired"}
        ]
        by_group = {
            str(membership["group_id"]): membership for membership in memberships
        }
        upcoming = [
            group
            for group in groups.list_upcoming(list(by_group))
            if _actionable_for_member(group, by_group[str(group["id"])])
        ]
        group = _first_group_with_availability(
            upcoming,
            free_blocks.list_for_student(student.id),
            by_group,
        )
    except NoSuggestionError:
        return NowResponse(gap=_next_gap(student), group=None)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load the current group suggestion",
        ) from exc

    try:
        return NowResponse(
            gap=gap_of(group),
            group=group_out(client, group, student.id),
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load the current group suggestion",
        ) from exc


def _actionable_for_member(group: dict[str, Any], membership: dict[str, Any]) -> bool:
    deadline = _invitation_deadline(group)
    now = datetime.now(timezone.utc)
    # A meeting that has already ended is nothing to act on, even while its
    # stored status still says confirmed or active.
    ends = datetime.combine(
        date.fromisoformat(str(group["on_date"])),
        time.fromisoformat(_short_time(str(group["end_time"]))),
        tzinfo=APPLICATION_TIMEZONE,
    )
    if now >= ends:
        return False
    if str(group.get("status")) == "forming" and now >= deadline:
        return False
    return not (
        membership.get("invitation_status") == "invited" and now >= deadline
    )


def _invitation_deadline(group: dict[str, Any]) -> datetime:
    value = group.get("invite_expires_at")
    if value is None:
        raise RepositoryError("Database returned no invitation deadline")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RepositoryError("Database returned an invalid invitation deadline")
    return parsed


def _next_gap(student: store.Student) -> GapOut | None:
    if not student.free_blocks:
        return None

    moment = datetime.now()
    today = moment.weekday()
    current = moment.time()

    def distance(block: tuple[int, time, time]) -> tuple[int, time]:
        day, start, _end = block
        days = (day - today) % 7
        if days == 0 and start <= current:
            days = 7
        return days, start

    day, start, end = min(student.free_blocks, key=distance)
    return GapOut(
        day=DAY_NAMES[day],
        start=start.strftime("%H:%M"),
        end=end.strftime("%H:%M"),
    )


def _first_group_with_availability(
    groups: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    memberships: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    for group in groups:
        # A group the student has joined is theirs whatever their schedule
        # says: "I'm free now" exists for a cancelled class, and an open
        # group only has to overlap a gap, not fit inside one.
        membership = (memberships or {}).get(str(group["id"]))
        if membership is not None and membership.get("invitation_status") == "accepted":
            return group
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
