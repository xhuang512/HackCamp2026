from datetime import date, time
from typing import Any

from app.repositories.base import RecordNotFoundError, execute


class GroupRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_upcoming(self, group_ids: list[str]) -> list[dict[str, Any]]:
        if not group_ids:
            return []
        return execute(
            self.client.table("groups")
            .select(
                "id,on_date,start_time,end_time,building_id,mode,status,created_at"
            )
            .in_("id", group_ids)
            .in_("status", ["proposed", "active"])
            .gte("on_date", date.today().isoformat())
            .order("on_date")
            .order("start_time"),
            "read upcoming groups",
        )

    def list_open_for_date(self, on_date: date) -> list[dict[str, Any]]:
        return execute(
            self.client.table("groups")
            .select(
                "id,on_date,start_time,end_time,building_id,mode,status,created_at"
            )
            .eq("on_date", on_date.isoformat())
            .in_("status", ["proposed", "active"])
            .order("start_time")
            .order("id"),
            "read existing groups for matching date",
        )

    def create(
        self,
        *,
        on_date: date,
        start_time: time,
        end_time: time,
        building_id: int,
    ) -> dict[str, Any]:
        rows = execute(
            self.client.table("groups").insert(
                {
                    "on_date": on_date.isoformat(),
                    "start_time": start_time.isoformat(timespec="minutes"),
                    "end_time": end_time.isoformat(timespec="minutes"),
                    "building_id": building_id,
                    "mode": "social",
                    "status": "proposed",
                }
            ),
            "create matched group",
        )
        if not rows:
            raise RecordNotFoundError("Database did not return the created group")
        return rows[0]

    def delete(self, group_id: str) -> None:
        execute(
            self.client.table("groups").delete().eq("id", group_id),
            "roll back matched group",
        )

    def building_name(self, building_id: int | None) -> str:
        if building_id is None:
            return "To be announced"
        rows = execute(
            self.client.table("buildings")
            .select("id,name")
            .eq("id", building_id)
            .limit(1),
            "read group building",
        )
        if not rows:
            raise RecordNotFoundError("Group building was not found")
        return str(rows[0]["name"])
