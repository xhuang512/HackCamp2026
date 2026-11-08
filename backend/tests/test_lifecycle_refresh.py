import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.lifecycle_refresh import LifecycleRefresher, refresh_lifecycle_rows
from tests.fakes import FakeSupabase, seed_tables


class LifecycleRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)
        self.tables = seed_tables()
        self.group = self.tables["groups"][0]
        self.group.update(
            {
                "on_date": "2026-11-08",
                "start_time": "13:00:00",
                "end_time": "15:00:00",
                "invite_expires_at": "2026-11-08T19:50:00+00:00",
                "confirmed_at": None,
                "status_changed_at": "2026-11-08T19:00:00+00:00",
            }
        )
        self.database = FakeSupabase(self.tables)
        self.group = self.database.tables["groups"][0]

    def test_expired_invitations_are_persisted_and_small_group_dissolves(self) -> None:
        self.group["status"] = "forming"
        self.database.tables["group_members"][0]["invitation_status"] = "accepted"
        self.database.tables["group_members"][1]["invitation_status"] = "invited"

        refresh_lifecycle_rows(self.database, at=self.now)

        self.assertEqual(self.group["status"], "dissolved")
        self.assertEqual(
            self.database.tables["group_members"][1]["invitation_status"],
            "expired",
        )

    def test_confirmed_group_advances_to_active_at_start(self) -> None:
        self._make_confirmed_group()
        at_start = datetime(2026, 11, 8, 21, 0, tzinfo=timezone.utc)

        refresh_lifecycle_rows(self.database, at=at_start)

        self.assertEqual(self.group["status"], "active")

    def test_confirmed_group_catches_up_to_completed_after_end(self) -> None:
        self._make_confirmed_group()
        self.group["on_date"] = "2026-11-07"
        self.group["invite_expires_at"] = "2026-11-07T19:50:00+00:00"
        self.group["confirmed_at"] = "2026-11-07T19:45:00+00:00"
        after_end = datetime(2026, 11, 8, 23, 1, tzinfo=timezone.utc)

        refresh_lifecycle_rows(self.database, at=after_end)

        self.assertEqual(self.group["status"], "completed")

    def test_two_reads_inside_fifteen_seconds_refresh_once(self) -> None:
        ticks = iter((100.0, 110.0, 116.0))
        refresher = LifecycleRefresher(
            monotonic=lambda: next(ticks),
            now=lambda: self.now,
        )

        with patch("app.lifecycle_refresh.refresh_lifecycle_rows") as refresh:
            refresher.refresh(self.database)
            refresher.refresh(self.database)
            refresher.refresh(self.database)

        self.assertEqual(refresh.call_count, 2)

    def test_refresh_error_is_logged_and_does_not_escape(self) -> None:
        refresher = LifecycleRefresher(
            monotonic=lambda: 100.0,
            now=lambda: self.now,
        )

        with (
            patch(
                "app.lifecycle_refresh.refresh_lifecycle_rows",
                side_effect=RuntimeError("offline"),
            ),
            self.assertLogs("app.lifecycle_refresh", level="ERROR"),
        ):
            refresher.refresh(self.database)

    def _make_confirmed_group(self) -> None:
        self.group["status"] = "confirmed"
        self.group["confirmed_at"] = (self.now - timedelta(hours=1)).isoformat()
        members = self.database.tables["group_members"]
        while len(members) < 3:
            members.append(dict(members[0]))
        for index, member in enumerate(members[:3]):
            member["student_id"] = f"student-{index}"
            member["invitation_status"] = "accepted"


if __name__ == "__main__":
    unittest.main()
