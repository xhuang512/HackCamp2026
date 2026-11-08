from datetime import date, datetime, time, timedelta
from typing import Any

from app.constants import CONFIRMED, FORMING, LIVE_GROUP_STATES
from app.repositories.base import RecordNotFoundError, RepositoryError, execute
from app.repositories.buildings import COLUMNS as BUILDING_COLUMNS
from app.timezones import APPLICATION_TIMEZONE

COLUMNS = (
    "id,on_date,start_time,end_time,building_id,mode,status,created_at,"
    "invite_expires_at,confirmed_at,status_changed_at"
)

SPOT_HIDDEN = "To be announced"

# How long before the meeting a matched group stops taking answers. A
# short-notice group (I'm free now) passes a lead of zero instead: its
# invitations stay open until the meeting starts, which the database's
# groups_invite_deadline_check (deadline <= start) still allows.
INVITATION_LEAD = timedelta(minutes=10)


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
        return execute(
            self.client.table("groups")
            .select(COLUMNS)
            .eq("on_date", on_date.isoformat())
            .in_("status", ["forming", "confirmed", "active"])
            .order("start_time")
            .order("id"),
            "read groups for matching date",
        )

    def list_open_for_date(self, on_date: date) -> list[dict[str, Any]]:
        """Compatibility alias retained for older callers and tests."""
        return self.list_for_matching_date(on_date)

    def list_from(self, on_date: date) -> list[dict[str, Any]]:
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
        invitation_lead: timedelta = INVITATION_LEAD,
    ) -> dict[str, Any]:
        if invitation_lead < timedelta(0):
            raise ValueError("invitation lead cannot be negative")
        meeting_start = datetime.combine(
            on_date,
            start_time,
            tzinfo=APPLICATION_TIMEZONE,
        )
        invite_expires_at = meeting_start - invitation_lead
        if invite_expires_at <= datetime.now(APPLICATION_TIMEZONE):
            raise RepositoryError(
                "Cannot create a group after its invitation deadline"
            )
        payload: dict[str, Any] = {
            "on_date": on_date.isoformat(),
            "start_time": start_time.isoformat(timespec="minutes"),
            "end_time": end_time.isoformat(timespec="minutes"),
            "building_id": building_id,
            "mode": mode,
            "status": status,
            "invite_expires_at": invite_expires_at.isoformat(),
        }
        if status == CONFIRMED:
            payload["confirmed_at"] = datetime.now(APPLICATION_TIMEZONE).isoformat()
        rows = execute(
            self.client.table("groups").insert(payload),
            "create matched group",
        )
        if not rows:
            raise RecordNotFoundError("Database did not return the created group")
        return rows[0]

    def set_status(self, group_id: str, status: str) -> None:
        now = datetime.now(APPLICATION_TIMEZONE).isoformat()
        payload: dict[str, Any] = {"status": status, "status_changed_at": now}
        if status == CONFIRMED:
            payload["confirmed_at"] = now
        execute(
            self.client.table("groups").update(payload).eq("id", group_id),
            "update group status",
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
