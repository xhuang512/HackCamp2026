"""GET /me/now: the next gap and the group suggested for it.

The one screen the whole app is for, so this route carries the privacy rules
rather than trusting the frontend with them. The assembly lives in
app/groups_view.py, shared with GET /groups/{id} and the check-in route so
all three answer identically.

The response moved to the shape docs/AGENTS.md specifies. What changed from
the merged version, for anyone reading a diff: `response` became `my_state`
with AGENTS.md's member states, `state`, `joined_count`, `checked_in_count`,
`seats_left` and `needs` were added, `spot` is now null while the group is
forming instead of a building reading "To be announced", and no suggestion
returns {"gap": …, "group": null} instead of {"status": "waiting"}.
"""

import logging
from datetime import date, datetime, time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app import store
from app.auth import onboarded_user
from app.db import get_db_client
from app.groups_view import DAY_NAMES, gap_of, group_out
from app.models import GapOut, NowResponse
from app.repositories import RecordNotFoundError, RepositoryError
from app.repositories.free_blocks import FreeBlockRepository
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository

router = APIRouter(tags=["students"])
logger = logging.getLogger(__name__)


# POST /students used to live here. It now lives in routers/identity.py,
# because the frontend sends the signup branch's richer body
# (preset_id/free_blocks, ask_me_about, visibility, guest) and expects
# {student, aha, guest_token} back, which this version did not return.
# The Supabase student repository has no identity columns wired up yet, so
# the surviving implementation is the store.py one. Porting it is the job
# that retires that split.


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
) -> NowResponse:
    free_blocks = FreeBlockRepository(client)
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    try:
        memberships = [
            membership
            for membership in members.list_for_student(student.id)
            # A declined group is not a suggestion any more. An expired one
            # never became one.
            if membership["response"] not in {"declined", "expired", "skipped"}
        ]
        upcoming = groups.list_upcoming(
            [str(membership["group_id"]) for membership in memberships]
        )
        group = _first_group_with_availability(
            upcoming,
            free_blocks.list_for_student(student.id),
        )
    except NoSuggestionError:
        # No group, but the gap is still worth sending: the screen says
        # "your next gap" above the open groups it falls back to.
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


def _next_gap(student: store.Student) -> GapOut | None:
    """The student's own next free block, when no group names one.

    Sorted by "days from today, then start time", so Thursday reads as sooner
    than Monday when today is Wednesday.
    """
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
