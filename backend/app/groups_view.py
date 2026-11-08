"""Turning group rows into what a student is allowed to see.

One module, because three routes answer the same question and the privacy
rules in AGENTS.md have to come out the same way in all three:

  GET /me/now               the suggested group
  GET /groups/{id}          the group after joining
  POST /groups/{id}/checkin the counts after a scan

The rules this file enforces, so no route has to remember them:

  * The meeting spot is hidden until the group is confirmed.
  * A group confirms at MIN_GROUP_SIZE joined members, not when everyone has
    answered.
  * First names go only to a caller who has joined, and only name members who
    have joined themselves. An invitation is not membership.
  * A caller who is not a member gets nothing from here at all.
"""

from datetime import date
from typing import Any

from .constants import (
    CONFIRMED,
    DECLINED,
    EXPIRED,
    FORMING,
    JOINED,
    LEGACY_CANCELLED,
    LEGACY_PROPOSED,
    MAX_GROUP_SIZE,
    MIN_GROUP_SIZE,
)
from .models import GapOut, GroupOut, MeetingSpot
from .repositories.group_members import GroupMemberRepository, state_of
from .repositories.groups import GroupRepository
from .repositories.students import StudentRepository

DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

# No distance table exists yet, so every walk is reported as this many
# minutes. A made-up number is worse than an honest placeholder, and the
# field is in the contract, so it stays until buildings carry distances.
PLACEHOLDER_WALK_MIN = 5


def live_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Members who are still part of the group: invited or joined."""
    return [
        member
        for member in members
        if state_of(member) not in {DECLINED, EXPIRED}
    ]


def joined_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [member for member in members if member.get("response") == JOINED]


def checked_in_members(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        member
        for member in joined_members(members)
        if member.get("arrived_at") is not None
    ]


def state_for(group: dict[str, Any], members: list[dict[str, Any]]) -> str:
    """The group state, derived rather than trusted.

    The stored status is authoritative once a group is active, completed or
    dissolved. Between forming and confirmed it is a count, and deriving it
    means a group cannot sit at `forming` with four joined members because
    one update failed.
    """
    stored = str(group.get("status") or FORMING)
    if stored in {FORMING, CONFIRMED, LEGACY_PROPOSED}:
        return CONFIRMED if len(joined_members(members)) >= MIN_GROUP_SIZE else FORMING
    if stored == LEGACY_CANCELLED:
        return "dissolved"
    return stored


def gap_of(group: dict[str, Any]) -> GapOut:
    on_date = date.fromisoformat(str(group["on_date"]))
    return GapOut(
        day=DAY_NAMES[on_date.weekday()],
        start=str(group["start_time"])[:5],
        end=str(group["end_time"])[:5],
    )


def group_out(
    client: Any,
    group: dict[str, Any],
    caller_id: str,
    *,
    members: list[dict[str, Any]] | None = None,
) -> GroupOut:
    """The group as this caller may see it."""
    groups = GroupRepository(client)
    students = StudentRepository(client)
    group_id = str(group["id"])

    all_members = (
        GroupMemberRepository(client).list_for_group(group_id)
        if members is None
        else members
    )
    mine = next(
        (m for m in all_members if str(m["student_id"]) == caller_id),
        None,
    )
    joined = joined_members(all_members)
    state = state_for(group, all_members)

    # Names: only to a joined caller, and only of joined members.
    names: list[str] = []
    if mine is not None and mine.get("response") == JOINED:
        joined_ids = [str(m["student_id"]) for m in joined]
        by_id = students.public_names(joined_ids)
        names = [by_id[item] for item in joined_ids if item in by_id]

    # What they share is safe before joining: it is a count or a label held
    # by two or more members, never one person's course.
    shared = students.shared_signals([str(m["student_id"]) for m in live_members(all_members)])

    spot = None
    if state != FORMING and group.get("building_id") is not None:
        spot = MeetingSpot(
            building=groups.building_name(group.get("building_id")),
            walk_min=PLACEHOLDER_WALK_MIN,
        )

    joined_count = len(joined)
    return GroupOut(
        id=group_id,
        state=state,
        mode=str(group.get("mode") or "social"),
        members=names,
        shared=shared,
        spot=spot,
        joined_count=joined_count,
        checked_in_count=len(checked_in_members(all_members)),
        seats_left=max(MAX_GROUP_SIZE - joined_count, 0),
        my_state=state_of(mine) if mine is not None else "invited",
        needs=max(MIN_GROUP_SIZE - joined_count, 0),
    )
