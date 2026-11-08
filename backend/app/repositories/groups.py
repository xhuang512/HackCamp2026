from datetime import date, datetime, time, timedelta
from typing import Any

from app.repositories.base import RecordNotFoundError, RepositoryError, execute
from app.timezones import APPLICATION_TIMEZONE



class GroupRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_upcoming(self, group_ids: list[str]) -> list[dict[str, Any]]:
        if not group_ids:
            return []
        return execute(
            self.client.table("groups")
            .select(self._select_columns())
            .in_("id", group_ids)
            .in_("status", ["forming", "confirmed", "active"])
            .gte("on_date", date.today().isoformat())
            .order("on_date")
            .order("start_time"),
            "read upcoming groups",
        )

    def get(self, group_id: str) -> dict[str, Any]:
        rows = execute(
            self.client.table("groups")
            .select(self._select_columns())
            .eq("id", group_id)
            .limit(1),
            "read group",
        )
        if not rows:
            raise RecordNotFoundError("Group was not found")
        return rows[0]

    def list_for_matching_date(self, on_date: date) -> list[dict[str, Any]]:
        """Return groups that can block assignment or accept more invitations."""
        return execute(
            self.client.table("groups")
            .select(self._select_columns())
            .eq("on_date", on_date.isoformat())
            .in_("status", ["forming", "confirmed", "active"])
            .order("start_time")
            .order("id"),
            "read groups for matching date",
        )

    def create(
        self,
        *,
        on_date: date,
        start_time: time,
        end_time: time,
        building_id: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "on_date": on_date.isoformat(),
            "start_time": start_time.isoformat(timespec="minutes"),
            "end_time": end_time.isoformat(timespec="minutes"),
            "building_id": building_id,
            "mode": "social",
            "status": "forming",
        }
        meeting_start = datetime.combine(
            on_date,
            start_time,
            tzinfo=APPLICATION_TIMEZONE,
        )
        invite_expires_at = meeting_start - timedelta(minutes=10)
        if invite_expires_at <= datetime.now(APPLICATION_TIMEZONE):
            raise RepositoryError(
                "Cannot create a group after its invitation deadline"
            )
        payload["invite_expires_at"] = invite_expires_at.isoformat()
        rows = execute(
            self.client.table("groups").insert(
                payload
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

    @staticmethod
    def _select_columns() -> str:
        return (
            "id,on_date,start_time,end_time,building_id,mode,status,created_at,"
            "invite_expires_at,confirmed_at,status_changed_at"
        )
