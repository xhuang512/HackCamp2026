from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from app.constants import DECLINED, MAX_GROUP_SIZE
from app.engine import GroupPlan, form_groups, pick_spot
from app.repositories import RepositoryError
from app.repositories.buildings import BuildingRepository
from app.repositories.free_blocks import FreeBlockRepository
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository
from app.repositories.students import StudentRepository


@dataclass(frozen=True)
class MatchingResult:
    target_date: date
    plans: tuple[GroupPlan, ...]
    created_group_ids: tuple[str, ...]
    filled_group_ids: tuple[str, ...]
    added_memberships: int
    already_assigned_students: int


@dataclass(frozen=True)
class GroupAddition:
    group_id: str
    student_ids: tuple[str, ...]


def run_matching(
    client: Any,
    target_date: date,
    *,
    persist: bool,
) -> MatchingResult:
    """Plan or persist simple groups for one calendar date.

    Existing proposed/active memberships on the date are excluded, making
    serial CLI reruns idempotent for already assigned students. Compatible
    existing groups are filled to five before new groups are formed.
    """
    students = StudentRepository(client)
    free_blocks = FreeBlockRepository(client)
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    matchable_ids = [str(row["id"]) for row in students.list_matchable()]
    existing_groups = groups.list_open_for_date(target_date)
    existing_memberships = members.list_for_groups(
        [str(group["id"]) for group in existing_groups]
    )
    assigned_ids = {
        str(membership["student_id"]) for membership in existing_memberships
    }
    available_ids = [
        student_id for student_id in matchable_ids if student_id not in assigned_ids
    ]
    blocks = free_blocks.list_for_students(
        available_ids,
        day=target_date.weekday(),
    )
    additions = _plan_existing_group_additions(
        existing_groups,
        existing_memberships,
        blocks,
    )
    added_ids = {
        student_id
        for addition in additions
        for student_id in addition.student_ids
    }
    plans = tuple(
        form_groups(
            [row for row in blocks if str(row["student_id"]) not in added_ids]
        )
    )

    if not persist or (not additions and not plans):
        return MatchingResult(
            target_date=target_date,
            plans=plans,
            created_group_ids=(),
            filled_group_ids=tuple(item.group_id for item in additions),
            added_memberships=sum(len(item.student_ids) for item in additions),
            already_assigned_students=len(assigned_ids),
        )

    buildings = BuildingRepository(client).list_all() if plans else []
    if plans and not buildings:
        raise RepositoryError("A valid building is required for a new group")
    spots = (
        students.list_spot_ids(
            [student_id for plan in plans for student_id in plan.student_ids]
        )
        if plans
        else {}
    )
    filled_ids: list[str] = []
    for addition in additions:
        members.create_pending(addition.group_id, addition.student_ids)
        filled_ids.append(addition.group_id)

    created_ids: list[str] = []
    for index, plan in enumerate(plans):
        created: dict[str, Any] | None = None
        try:
            created = groups.create(
                on_date=target_date,
                start_time=plan.start_time,
                end_time=plan.end_time,
                building_id=pick_spot(
                    buildings,
                    [spots.get(student_id, []) for student_id in plan.student_ids],
                    spread=index,
                ),
            )
            group_id = str(created["id"])
            members.create_pending(group_id, plan.student_ids)
            created_ids.append(group_id)
        except RepositoryError:
            if created is not None and "id" in created:
                try:
                    groups.delete(str(created["id"]))
                except RepositoryError:
                    pass
            raise

    return MatchingResult(
        target_date=target_date,
        plans=plans,
        created_group_ids=tuple(created_ids),
        filled_group_ids=tuple(filled_ids),
        added_memberships=sum(len(item.student_ids) for item in additions),
        already_assigned_students=len(assigned_ids),
    )


def next_matching_dates(
    weekdays: set[int],
    *,
    from_date: date | None = None,
) -> tuple[date, ...]:
    """Return the next calendar occurrence of each weekly availability day."""
    start = from_date or date.today()
    dates: list[date] = []
    for weekday in sorted(weekdays):
        if not 0 <= weekday <= 6:
            raise ValueError(f"invalid weekday: {weekday}")
        days_ahead = (weekday - start.weekday()) % 7
        dates.append(start + timedelta(days=days_ahead))
    return tuple(sorted(dates))


def _plan_existing_group_additions(
    groups: list[dict[str, Any]],
    memberships: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    *,
    max_size: int = MAX_GROUP_SIZE,
) -> tuple[GroupAddition, ...]:
    by_group: dict[str, list[dict[str, Any]]] = {
        str(group["id"]): [] for group in groups
    }
    for membership in memberships:
        by_group.setdefault(str(membership["group_id"]), []).append(membership)

    remaining = {str(block["student_id"]) for block in blocks}
    additions: list[GroupAddition] = []
    for group in groups:
        group_id = str(group["id"])
        current = by_group.get(group_id, [])
        # A declined group is left unchanged. Replacing declined members needs
        # a separate lifecycle policy so it cannot accidentally reveal its spot.
        if any(member["response"] == DECLINED for member in current):
            continue
        capacity = max_size - len(current)
        if capacity <= 0:
            continue
        compatible = sorted(
            student_id
            for student_id in remaining
            if _student_covers_group(student_id, group, blocks)
        )[:capacity]
        if not compatible:
            continue
        additions.append(GroupAddition(group_id, tuple(compatible)))
        remaining.difference_update(compatible)
    return tuple(additions)


def _student_covers_group(
    student_id: str,
    group: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> bool:
    group_start = time.fromisoformat(str(group["start_time"]))
    group_end = time.fromisoformat(str(group["end_time"]))
    return any(
        str(block["student_id"]) == student_id
        and time.fromisoformat(str(block["start_time"])) <= group_start
        and time.fromisoformat(str(block["end_time"])) >= group_end
        for block in blocks
    )
