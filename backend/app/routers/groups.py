"""Groups: join, skip, start one, look at yours, check in.

The join and skip routes are the ones that came over with the merged
backend. Their paths and their response bodies are unchanged, because the
frontend and the tests both already speak them. Everything below them is new
and follows the API contract in docs/AGENTS.md.
"""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict
from supabase import Client

from app import codes, store
from app.auth import get_current_student_id, onboarded_user
from app.constants import (
    CONFIRMED,
    DECLINED,
    FORMING,
    JOINED,
    MAX_GROUP_SIZE,
    MIN_GROUP_SIZE,
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
from app.models import (
    CheckInCodeOut,
    CheckInRequest,
    CheckInResult,
    CreateGroupRequest,
    GroupOut,
    OpenGroupOut,
)
from app.repositories import RecordNotFoundError, RepositoryError
from app.repositories.buildings import BuildingRepository
from app.repositories.free_blocks import FreeBlockRepository
from app.repositories.group_members import GroupMemberRepository, state_of
from app.repositories.groups import GroupRepository
from app.repositories.students import StudentRepository

router = APIRouter(prefix="/groups", tags=["groups"])

# How long an "I'm free now" group runs when the student has no free block
# covering this moment. Long enough to meet somebody, short enough that it
# expires on its own during a demo.
DEFAULT_NOW_MINUTES = 120


class GroupResponseUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"group_id": "g_41", "response": "joined"}}
    )

    group_id: str
    # The wire values the merged frontend and tests already use. The stored
    # member states are AGENTS.md's invited/joined/declined/expired, and
    # _STORED maps between the two so neither side has to change.
    response: Literal["joined", "skipped"]


_STORED = {"joined": JOINED, "skipped": DECLINED}


# ---------------------------------------------------------------- responding


@router.post(
    "/{id}/join",
    response_model=GroupResponseUpdate,
    summary="Join a suggested or open group",
)
def join_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _respond(client, id, student_id, "joined")


@router.post(
    "/{id}/skip",
    response_model=GroupResponseUpdate,
    summary="Decline a suggested group",
)
def skip_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _respond(client, id, student_id, "skipped")


def _respond(
    client: Client,
    group_id: str,
    student_id: str,
    response: Literal["joined", "skipped"],
) -> GroupResponseUpdate:
    members = GroupMemberRepository(client)
    try:
        members.update_response(group_id, student_id, _STORED[response])
        _settle_state(client, group_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update group membership",
        ) from exc
    return GroupResponseUpdate(group_id=group_id, response=response)


def _settle_state(client: Client, group_id: str) -> None:
    """Move the group between forming and confirmed after an answer.

    The spot becomes visible at exactly this moment, so the transition is
    worth storing rather than only deriving: the projector counts groups by
    status and should not have to count members to do it.
    """
    groups = GroupRepository(client)
    group = groups.get(group_id)
    stored = str(group.get("status") or FORMING)
    if stored not in {FORMING, CONFIRMED}:
        return
    members = GroupMemberRepository(client).list_for_group(group_id)
    wanted = CONFIRMED if len(joined_members(members)) >= MIN_GROUP_SIZE else FORMING
    if wanted != stored:
        groups.set_status(group_id, wanted)


# ------------------------------------------------------------- open groups


@router.get(
    "/open",
    response_model=list[OpenGroupOut],
    summary="Confirmed groups in the caller's gaps with seats left",
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
            if state_for(group, group_members) != CONFIRMED:
                continue
            seats_left = MAX_GROUP_SIZE - len(joined_members(group_members))
            if seats_left <= 0:
                continue
            if not _overlaps_a_gap(group, student):
                continue
            out.append(
                OpenGroupOut(
                    id=str(group["id"]),
                    gap=gap_of(group),
                    mode=str(group.get("mode") or "social"),
                    # The general area, which for a confirmed group with
                    # seats left is the building name. AGENTS.md allows it
                    # before joining; what stays hidden is who is there.
                    area=groups.building_name(group.get("building_id")),
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

    on_date, start, end = _slot_for(student, now=body.now)

    created = None
    try:
        created = groups.create(
            on_date=on_date,
            start_time=start,
            end_time=end,
            building_id=int(building["id"]),
            mode=body.mode,
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


def _slot_for(student: store.Student, *, now: bool) -> tuple[date, time, time]:
    """When the group meets.

    "I'm free now" starts at this minute and runs to the end of the free
    block covering it, or DEFAULT_NOW_MINUTES when the student is not
    supposed to be free at all. Someone whose class was cancelled is not
    lying about being free, so this does not refuse them.
    """
    moment = datetime.now()
    if now:
        today = moment.date()
        start = moment.time().replace(second=0, microsecond=0)
        covering = [
            block_end
            for day, block_start, block_end in student.free_blocks
            if day == today.weekday() and block_start <= start < block_end
        ]
        end = (
            max(covering)
            if covering
            else (moment + timedelta(minutes=DEFAULT_NOW_MINUTES)).time().replace(
                second=0, microsecond=0
            )
        )
        if end <= start:
            end = time(23, 59)
        return today, start, end

    if not student.free_blocks:
        raise HTTPException(
            status_code=422,
            detail="Add a schedule before starting a group for a gap.",
        )

    today = moment.weekday()
    current = moment.time()

    def distance(block: tuple[int, time, time]) -> tuple[int, time]:
        day, start, _end = block
        days = (day - today) % 7
        if days == 0 and start <= current:
            days = 7
        return days, start

    day, start, end = min(student.free_blocks, key=distance)
    days_ahead = (day - today) % 7
    if days_ahead == 0 and start <= current:
        days_ahead = 7
    return moment.date() + timedelta(days=days_ahead), start, end


# ------------------------------------------------------------- one group


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


@router.get(
    "/{id}/checkin-code",
    response_model=CheckInCodeOut,
    summary="The caller's current check-in code",
    description=(
        "Signed, rotates every 30 seconds, and only validates between "
        "members of the same group. There are no building codes."
    ),
)
def get_checkin_code(
    id: Annotated[str, Path(description="Opaque group identifier")],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> CheckInCodeOut:
    all_members, _ = _member_and_group(client, id, student_id)
    mine = next(m for m in all_members if str(m["student_id"]) == student_id)
    if mine.get("response") != JOINED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the group before checking in.",
        )
    issued = codes.issue(student_id)
    return CheckInCodeOut(code=issued.code, expires_in=issued.expires_in)


@router.post(
    "/{id}/checkin",
    response_model=CheckInResult,
    summary="Submit a scanned groupmate's code",
    description=(
        "Checks both people in. Repeat scans of the same pair change "
        "nothing. A code from outside the group is rejected."
    ),
)
def post_checkin(
    id: Annotated[str, Path(description="Opaque group identifier")],
    body: CheckInRequest,
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> CheckInResult:
    all_members, group = _member_and_group(client, id, student_id)
    members = GroupMemberRepository(client)

    scanned_id = codes.read(body.code)
    # One answer for every bad code: wrong shape, bad signature, expired
    # window, or a member of another group. Telling a scanner which would
    # help nobody but a forger.
    if scanned_id is None or scanned_id == student_id:
        raise HTTPException(status_code=422, detail="That code is not valid.")
    if not any(str(m["student_id"]) == scanned_id for m in all_members):
        raise HTTPException(status_code=422, detail="That code is not valid.")

    try:
        changed = members.mark_arrived(id, (student_id, scanned_id))
        refreshed = members.list_for_group(id)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not record the check-in",
        ) from exc

    mine = next((m for m in refreshed if str(m["student_id"]) == student_id), None)
    return CheckInResult(
        joined_count=len(joined_members(refreshed)),
        checked_in_count=len(checked_in_members(refreshed)),
        my_state=state_of(mine) if mine is not None else "invited",
        counted=changed > 0,
    )
