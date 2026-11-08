"""GET /projector: the stage screen's numbers.

Public and never asks anyone to sign in, because it runs on a laptop plugged
into the projector rather than on a student's phone.

Nothing here is per-student. Counts and places only, and a count is not a
name, which is what makes this the one surface in the app with no auth at
all. It also means the MIN_GROUP_SIZE floor the map applies is unnecessary
here: a dot is a group, and a group is at least two people by definition.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.constants import ACTIVE, CONFIRMED, FORMING
from app.db import get_db_client
from app.groups_view import checked_in_members, live_members, state_for
from app.lifecycle_refresh import refresh_lifecycle
from app.models import ProjectorDot, ProjectorState
from app.repositories import RepositoryError
from app.repositories.buildings import BuildingRepository
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository

router = APIRouter(tags=["projector"])


@router.get(
    "/projector",
    response_model=ProjectorState,
    summary="Anonymous totals and dots for the stage",
    description=(
        "Aggregate totals only. Student names and timetable details are "
        "intentionally absent from this public surface."
    ),
)
def get_projector_state(
    client: Annotated[Client, Depends(get_db_client)],
    _lifecycle: Annotated[None, Depends(refresh_lifecycle)],
) -> ProjectorState:
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    try:
        buildings = {
            int(row["id"]): row for row in BuildingRepository(client).list_all()
        }
        today = date.today()
        live = [
            group
            for group in groups.list_from(today)
            if str(group["on_date"]) == today.isoformat()
        ]
        memberships = members.list_for_groups([str(group["id"]) for group in live])
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load the projector state",
        ) from exc

    by_group: dict[str, list[dict]] = {}
    for membership in memberships:
        by_group.setdefault(str(membership["group_id"]), []).append(membership)

    forming = confirmed = 0
    checked_in: set[str] = set()
    students: set[str] = set()
    dots: dict[int, int] = {}

    for group in live:
        group_members = by_group.get(str(group["id"]), [])
        state = state_for(group, group_members)
        if state == FORMING:
            forming += 1
        elif state in {CONFIRMED, ACTIVE}:
            confirmed += 1

        people = live_members(group_members)
        students.update(str(member["student_id"]) for member in people)
        checked_in.update(
            str(member["student_id"]) for member in checked_in_members(group_members)
        )

        building_id = group.get("building_id")
        if building_id is not None and int(building_id) in buildings:
            dots[int(building_id)] = dots.get(int(building_id), 0) + len(people)

    return ProjectorState(
        forming=forming,
        confirmed=confirmed,
        # The pitch metric: hangouts that actually happened, counted by
        # people who scanned a groupmate rather than by sessions opened.
        checked_in=len(checked_in),
        students=len(students),
        dots=[
            ProjectorDot(
                slug=str(buildings[building_id]["slug"]),
                name=str(buildings[building_id]["name"]),
                lat=float(buildings[building_id]["lat"]),
                lng=float(buildings[building_id]["lng"]),
                count=count,
            )
            for building_id, count in sorted(dots.items())
        ],
    )
