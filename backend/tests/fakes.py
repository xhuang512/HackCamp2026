from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo


def next_weekday(target: int) -> date:
    today = date.today()
    delta = (target - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


def seed_tables() -> dict[str, list[dict[str, Any]]]:
    group_date = next_weekday(1)
    group_start = datetime.combine(
        group_date,
        datetime.strptime("13:15", "%H:%M").time(),
        tzinfo=ZoneInfo("America/Vancouver"),
    )
    return {
        "tags": [
            {
                "id": 1,
                "slug": "transfer",
                "label": "Transfer student",
                "category": "student_type",
            },
        ],
        "languages": [{"code": "en", "name": "English"}],
        "courses": [{"id": 1, "code": "STAT 302", "title": "Introduction"}],
        "buildings": [
            {
                "id": 1,
                "slug": "nest",
                "name": "The Nest",
                "lat": 49.2665,
                "lng": -123.2497,
                "is_indoor": True,
            }
        ],
        "students": [
            {
                "id": "s_current",
                "first_name": "Maya",
                "paused": False,
                "deleted_at": None,
            },
            {
                "id": "s_other",
                "first_name": "Amir",
                "paused": False,
                "deleted_at": None,
            },
        ],
        "student_tags": [
            {"student_id": "s_current", "tag_id": 1},
            {"student_id": "s_other", "tag_id": 1},
        ],
        "student_languages": [
            {"student_id": "s_current", "language_code": "en"},
            {"student_id": "s_other", "language_code": "en"},
        ],
        "student_courses": [
            {"student_id": "s_current", "course_id": 1, "term": "2026W1"},
            {"student_id": "s_other", "course_id": 1, "term": "2026W1"},
        ],
        "free_blocks": [
            {
                "id": 1,
                "student_id": "s_current",
                "day": 1,
                "start_time": "13:00:00",
                "end_time": "15:00:00",
            }
        ],
        "groups": [
            {
                "id": "g_41",
                "on_date": group_date.isoformat(),
                "start_time": "13:15:00",
                "end_time": "14:30:00",
                "building_id": 1,
                "mode": "study",
                "status": "forming",
                "invite_expires_at": (group_start - timedelta(minutes=10)).isoformat(),
                "confirmed_at": None,
                "status_changed_at": "2026-11-07T00:00:00Z",
                "created_at": "2026-11-07T00:00:00Z",
            }
        ],
        "group_members": [
            {
                "group_id": "g_41",
                "student_id": "s_current",
                "invitation_status": "invited",
                "arrived_at": None,
            },
            {
                "group_id": "g_41",
                "student_id": "s_other",
                "invitation_status": "accepted",
                "arrived_at": None,
            },
        ],
    }


class FakeSupabase:
    """Small PostgREST query fake used by contract and repository tests."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None):
        self.tables = deepcopy(tables or seed_tables())

    def table(self, name: str) -> FakeQuery:
        self.tables.setdefault(name, [])
        return FakeQuery(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcQuery:
        return FakeRpcQuery(self, name, params)


class FakePostgrestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class FakeRpcQuery:
    def __init__(
        self,
        client: FakeSupabase,
        name: str,
        params: dict[str, Any],
    ):
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> SimpleNamespace:
        if self.name != "respond_to_group_invitation":
            raise FakePostgrestError("42883", f"Unknown RPC: {self.name}")

        group_id = str(self.params["p_group_id"])
        student_id = str(self.params["p_student_id"])
        target = str(self.params["p_response"])
        if target not in {"accepted", "declined"}:
            raise FakePostgrestError(
                "22023",
                "Invitation response must be accepted or declined",
            )
        group = next(
            (
                row
                for row in self.client.tables["groups"]
                if str(row["id"]) == group_id
            ),
            None,
        )
        if group is None:
            raise FakePostgrestError("P0002", "Group invitation was not found")
        member = next(
            (
                row
                for row in self.client.tables["group_members"]
                if str(row["group_id"]) == group_id
                and str(row["student_id"]) == student_id
            ),
            None,
        )
        if member is None:
            raise FakePostgrestError(
                "P0002",
                "No membership exists for the current student and group",
            )

        current = str(member["invitation_status"])
        if current != target:
            if group["status"] not in {"forming", "confirmed"}:
                raise FakePostgrestError(
                    "P0001",
                    f"Invitations cannot change while the group is {group['status']}",
                )
            deadline = datetime.fromisoformat(
                str(group["invite_expires_at"]).replace("Z", "+00:00")
            )
            if datetime.now(timezone.utc) >= deadline:
                raise FakePostgrestError(
                    "P0001",
                    "The invitation deadline has passed",
                )
            if current != "invited":
                raise FakePostgrestError(
                    "P0001",
                    f"Cannot change an {current} invitation to {target}",
                )
            member["invitation_status"] = target

        accepted_count = sum(
            row["invitation_status"] == "accepted"
            for row in self.client.tables["group_members"]
            if str(row["group_id"]) == group_id
        )
        if group["status"] == "forming" and accepted_count >= 3:
            now = datetime.now(timezone.utc).isoformat()
            group["status"] = "confirmed"
            group["confirmed_at"] = group.get("confirmed_at") or now
            group["status_changed_at"] = now

        return SimpleNamespace(
            data=[
                {
                    "group_id": group_id,
                    "student_id": student_id,
                    "invitation_status": member["invitation_status"],
                    "group_status": group["status"],
                    "accepted_count": accepted_count,
                    "invite_expires_at": group["invite_expires_at"],
                }
            ]
        )


class FakeQuery:
    def __init__(self, client: FakeSupabase, table: str):
        self.client = client
        self.table_name = table
        self.action = "select"
        self.payload: Any = None
        self.conflict_column: str | None = None
        self.filters: list[tuple[str, str, Any]] = []
        self.orders: list[str] = []
        self.max_rows: int | None = None

    def select(self, _columns: str) -> FakeQuery:
        self.action = "select"
        return self

    def insert(self, payload: Any) -> FakeQuery:
        self.action = "insert"
        self.payload = payload
        return self

    def upsert(self, payload: Any, *, on_conflict: str) -> FakeQuery:
        self.action = "upsert"
        self.payload = payload
        self.conflict_column = on_conflict
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self.action = "update"
        self.payload = payload
        return self

    def delete(self) -> FakeQuery:
        self.action = "delete"
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        self.filters.append(("in", column, values))
        return self

    def gte(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("gte", column, value))
        return self

    def is_(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(("is", column, value))
        return self

    def order(self, column: str) -> FakeQuery:
        self.orders.append(column)
        return self

    def limit(self, count: int) -> FakeQuery:
        self.max_rows = count
        return self

    def execute(self) -> SimpleNamespace:
        rows = self.client.tables[self.table_name]
        if self.action in {"insert", "upsert"}:
            payloads = self.payload if isinstance(self.payload, list) else [self.payload]
            created = []
            for payload in payloads:
                row = deepcopy(payload)
                if self.action == "upsert":
                    existing = next(
                        (
                            item
                            for item in rows
                            if item.get(self.conflict_column)
                            == row.get(self.conflict_column)
                        ),
                        None,
                    )
                    if existing is not None:
                        existing.update(row)
                        created.append(deepcopy(existing))
                        continue
                if self.table_name == "students":
                    row.setdefault("id", str(uuid4()))
                    row.setdefault("paused", False)
                    row.setdefault("deleted_at", None)
                if self.table_name == "groups":
                    row.setdefault("id", str(uuid4()))
                if self.table_name == "free_blocks":
                    row.setdefault("id", len(rows) + 1)
                # buildings.id is a smallserial in schema.sql, so
                # Postgres fills it and an upsert here has to as well.
                if self.table_name in {"tags", "courses", "buildings"}:
                    next_id = max(
                        (item.get("id", 0) for item in rows),
                        default=0,
                    ) + 1
                    row.setdefault("id", next_id)
                rows.append(row)
                created.append(deepcopy(row))
            return SimpleNamespace(data=created)

        matched = [row for row in rows if self._matches(row)]
        for column in reversed(self.orders):
            matched.sort(key=lambda row: row.get(column))
        if self.max_rows is not None:
            matched = matched[: self.max_rows]

        if self.action == "update":
            for row in matched:
                row.update(deepcopy(self.payload))
            return SimpleNamespace(data=deepcopy(matched))

        if self.action == "delete":
            deleted = deepcopy(matched)
            self.client.tables[self.table_name] = [
                row for row in rows if not self._matches(row)
            ]
            return SimpleNamespace(data=deleted)

        return SimpleNamespace(data=deepcopy(matched))

    def _matches(self, row: dict[str, Any]) -> bool:
        for operator, column, expected in self.filters:
            actual = row.get(column)
            if operator == "eq" and actual != expected:
                return False
            if operator == "in" and actual not in expected:
                return False
            if operator == "gte" and actual < expected:
                return False
            if operator == "is":
                if expected == "null" and actual is not None:
                    return False
                if expected != "null" and actual != expected:
                    return False
        return True
