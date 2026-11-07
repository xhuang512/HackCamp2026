from dataclasses import dataclass
from datetime import date
from typing import Any

from app.engine import GroupPlan, form_groups
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
    already_assigned_students: int


def run_matching(
    client: Any,
    target_date: date,
    *,
    persist: bool,
) -> MatchingResult:
    """Plan or persist simple groups for one calendar date.

    Existing proposed/active memberships on the date are excluded, making
    serial CLI reruns idempotent for already assigned students.
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
    plans = tuple(form_groups(blocks))

    if not persist or not plans:
        return MatchingResult(
            target_date=target_date,
            plans=plans,
            created_group_ids=(),
            already_assigned_students=len(assigned_ids),
        )

    building = BuildingRepository(client).first_available()
    created_ids: list[str] = []
    for plan in plans:
        created: dict[str, Any] | None = None
        try:
            created = groups.create(
                on_date=target_date,
                start_time=plan.start_time,
                end_time=plan.end_time,
                building_id=int(building["id"]),
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
        already_assigned_students=len(assigned_ids),
    )
