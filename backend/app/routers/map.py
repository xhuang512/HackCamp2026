"""GET /map: what is happening on campus, and where your group is meeting.

Two privacy rules live here and nowhere else:

  * Counts below MIN_GROUP_SIZE are not sent at all, so nobody can be singled
    out by a pin reading "1 student".
  * The caller's own group building is sent only once the group is confirmed,
    which is the same moment the Right now card reveals it.

Nothing in the request says where the caller is. There is deliberately no
parameter for a coordinate: the server decides what is public from the group
and building rows, and the phone never tells it where it is. The map page's
own position stays on the device. docs/MAP.md has the rest of that boundary.
"""

from datetime import date, datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app import store
from app.auth import onboarded_user
from app.constants import ACTIVE, CONFIRMED, MIN_GROUP_SIZE
from app.db import get_db_client
from app.groups_view import (
    checked_in_members,
    joined_members,
    live_members,
    spot_is_visible_to,
)
from app.models import BuildingActivity, MapResponse, MyGroupPin
from app.repositories import RepositoryError
from app.repositories.buildings import BuildingRepository
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository
from app.timezones import APPLICATION_TIMEZONE

router = APIRouter(tags=["map"])


@router.get(
    "/map",
    response_model=MapResponse,
    summary="Building activity, plus the caller's group building if confirmed",
    description=(
        "`free_count` is how many students are in a live group at that "
        "building today. Buildings with fewer than three are omitted "
        "entirely, so a quiet building is absent rather than shown as a "
        "small number."
    ),
)
def get_map(
    student: Annotated[store.Student, Depends(onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> MapResponse:
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)

    try:
        buildings = {
            int(row["id"]): row for row in BuildingRepository(client).list_all()
        }
        today = date.today()
        now = datetime.now(APPLICATION_TIMEZONE)
        live = [
            group
            for group in groups.list_from(today)
            if str(group["on_date"]) == today.isoformat()
        ]
        memberships = members.list_for_groups([str(group["id"]) for group in live])
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load the map",
        ) from exc

    by_group: dict[str, list[dict]] = {}
    for membership in memberships:
        by_group.setdefault(str(membership["group_id"]), []).append(membership)

    # Distinct students per building, so somebody in two groups at the same
    # place is one person on the map.
    heads: dict[int, set[str]] = {}
    groups_meeting: dict[int, int] = {}
    my_pin: MyGroupPin | None = None

    for group in live:
        building_id = group.get("building_id")
        if building_id is None or int(building_id) not in buildings:
            continue
        group_members = by_group.get(str(group["id"]), [])
        heads.setdefault(int(building_id), set()).update(
            str(member["student_id"]) for member in live_members(group_members)
        )

        end = datetime.combine(
            today,
            time.fromisoformat(str(group["end_time"])),
            tzinfo=APPLICATION_TIMEZONE,
        )
        if (
            str(group.get("status")) in {CONFIRMED, ACTIVE}
            and end > now
            and len(joined_members(group_members)) >= MIN_GROUP_SIZE
        ):
            groups_meeting[int(building_id)] = groups_meeting.get(int(building_id), 0) + 1

        if my_pin is not None:
            continue
        # The same rule as the group card's meeting spot, from the same
        # function: joined, and past forming. A pin carries the building's
        # coordinates, so an invited-only caller getting one would leak more
        # than the card does, not less.
        if not spot_is_visible_to(group, group_members, student.id):
            continue
        building = buildings[int(building_id)]
        my_pin = MyGroupPin(
            group_id=str(group["id"]),
            slug=str(building["slug"]),
            name=str(building["name"]),
            lat=float(building["lat"]),
            lng=float(building["lng"]),
            joined_count=len(joined_members(group_members)),
            checked_in_count=len(checked_in_members(group_members)),
        )

    activity = [
        BuildingActivity(
            slug=str(buildings[building_id]["slug"]),
            name=str(buildings[building_id]["name"]),
            lat=float(buildings[building_id]["lat"]),
            lng=float(buildings[building_id]["lng"]),
            free_count=len(students),
            groups_meeting=groups_meeting.get(building_id),
        )
        for building_id, students in sorted(heads.items())
        # The rule, in one line: a count under three is not publishable.
        if len(students) >= MIN_GROUP_SIZE
    ]

    return MapResponse(buildings=activity, my_group=my_pin)
