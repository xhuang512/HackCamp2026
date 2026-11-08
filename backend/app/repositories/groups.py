from datetime import date, time
from typing import Any

from app.constants import CONFIRMED, DISSOLVED, FORMING, LIVE_GROUP_STATES
from app.repositories.base import (
    RecordNotFoundError,
    RepositoryError,
    database_error_code,
    execute,
)
from app.repositories.buildings import COLUMNS as BUILDING_COLUMNS

COLUMNS = "id,on_date,start_time,end_time,building_id,mode,status,created_at"

# What a student is shown when the group is still forming. AGENTS.md: the
# spot is hidden until the group is confirmed, and the card says
# "Waiting for N more to confirm" instead.
SPOT_HIDDEN = "To be announced"


class GroupRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_upcoming(self, group_ids: list[str]) -> list[dict[str, Any]]:
        if not group_ids:
            return []
        return execute(
            self.client.table("groups")
            .select(COLUMNS)
            .in_("id", group_ids)
            .in_("status", list(LIVE_GROUP_STATES))
            .gte("on_date", date.today().isoformat())
            .order("on_date")
            .order("start_time"),
            "read upcoming groups",
        )

    def list_open_for_date(self, on_date: date) -> list[dict[str, Any]]:
        return execute(
            self.client.table("groups")
            .select(COLUMNS)
            .eq("on_date", on_date.isoformat())
            .in_("status", list(LIVE_GROUP_STATES))
            .order("start_time")
            .order("id"),
            "read existing groups for matching date",
        )

    def list_from(self, on_date: date) -> list[dict[str, Any]]:
        """Every live group from `on_date` onwards.

        The map and the projector both need all of them rather than one
        student's, so they cannot go through list_upcoming, which filters by
        membership.
        """
        return execute(
            self.client.table("groups")
            .select(COLUMNS)
            .in_("status", list(LIVE_GROUP_STATES))
            .gte("on_date", on_date.isoformat())
            .order("on_date")
            .order("start_time"),
            "read live groups",
        )

    def get(self, group_id: str) -> dict[str, Any]:
        rows = execute(
            self.client.table("groups").select(COLUMNS).eq("id", group_id).limit(1),
            "read group",
        )
        if not rows:
            raise RecordNotFoundError("That group does not exist")
        return rows[0]

    def create(
        self,
        *,
        on_date: date,
        start_time: time,
        end_time: time,
        building_id: int,
        mode: str = "social",
        status: str = FORMING,
    ) -> dict[str, Any]:
        def insert(stored_status: str) -> list[dict[str, Any]]:
            return execute(
                self.client.table("groups").insert(
                    {
                        "on_date": on_date.isoformat(),
                        "start_time": start_time.isoformat(timespec="minutes"),
                        "end_time": end_time.isoformat(timespec="minutes"),
                        "building_id": building_id,
                        "mode": mode,
                        "status": stored_status,
                    }
                ),
                "create matched group",
            )
        try:
            rows = insert(status)
        except RepositoryError as exc:
            if database_error_code(exc) != "23514" or status not in {
                FORMING,
                CONFIRMED,
            }:
                raise
            rows = insert("proposed")
        if not rows:
            raise RecordNotFoundError("Database did not return the created group")
        return rows[0]

    def set_status(self, group_id: str, status: str) -> None:
        try:
            execute(
                self.client.table("groups").update({"status": status}).eq("id", group_id),
                "update group status",
            )
        except RepositoryError as exc:
            if database_error_code(exc) != "23514":
                raise
            legacy = {
                FORMING: "proposed",
                CONFIRMED: "proposed",
                DISSOLVED: "cancelled",
            }
            if status not in legacy:
                raise
            execute(
                self.client.table("groups").update({"status": legacy[status]}).eq("id", group_id),
                "update legacy group status",
            )

    def delete(self, group_id: str) -> None:
        execute(
            self.client.table("groups").delete().eq("id", group_id),
            "roll back matched group",
        )

    def building_name(self, building_id: int | None) -> str:
        if building_id is None:
            return SPOT_HIDDEN
        return str(self.building(building_id)["name"])

    def building(self, building_id: int) -> dict[str, Any]:
        """The full building row, because the map needs its coordinates and
        its slug, not only the name."""
        rows = execute(
            self.client.table("buildings")
            .select(BUILDING_COLUMNS)
            .eq("id", building_id)
            .limit(1),
            "read group building",
        )
        if not rows:
            raise RecordNotFoundError("Group building was not found")
        return rows[0]
