"""I'm free now, and joining a group that is still forming.

Covers the path a live demo depends on: one student starts a group for right
now, two others find it in GET /groups/open and join, the third acceptance
confirms it, and every joined member then sees it on Right now.
"""

import unittest
from datetime import datetime, time, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import store
from app.auth import create_guest_session
from app.db import get_db_client
from app.main import app
from app.routers.groups import FORMING_AREA, NOW_LEAD_MINUTES
from app.timezones import APPLICATION_TIMEZONE
from tests.fakes import FakeSupabase


def _free_around_now() -> list[tuple[int, time, time]]:
    """A free block today that covers the next few hours, Vancouver time."""
    now = datetime.now(APPLICATION_TIMEZONE)
    start = (now - timedelta(minutes=30)).time().replace(second=0, microsecond=0)
    if (now - timedelta(minutes=30)).date() != now.date():
        start = time(0, 0)
    return [(now.weekday(), start, time(23, 59))]


class ShortNoticeGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def setUp(self) -> None:
        self.environment = patch.dict(
            "os.environ",
            {"GUEST_SESSION_SECRET": "test-only-secret-that-is-at-least-32-bytes"},
            clear=True,
        )
        self.environment.start()
        store.reset()
        self.database = FakeSupabase()
        app.dependency_overrides[get_db_client] = lambda: self.database
        self.headers = {}
        for student_id in ("s_founder", "s_second", "s_third", "s_fourth"):
            store.put(
                store.Student(
                    id=student_id,
                    first_name=student_id.split("_")[1].title(),
                    auth_sub=f"guest:{student_id}",
                    is_guest=True,
                    free_blocks=_free_around_now(),
                )
            )
            self.database.tables["students"].append(
                {"id": student_id, "first_name": student_id, "paused": False, "deleted_at": None}
            )
            self.headers[student_id] = {
                "Authorization": f"Bearer {create_guest_session(student_id)}"
            }

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()

    def _start_now(self, who: str = "s_founder") -> dict:
        response = self.client.post(
            "/groups",
            json={"building": "nest", "mode": "social", "now": True},
            headers=self.headers[who],
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _row(self, group_id: str) -> dict:
        return next(g for g in self.database.tables["groups"] if g["id"] == group_id)

    def test_now_group_starts_shortly_and_takes_answers_until_it_starts(self) -> None:
        before = datetime.now(APPLICATION_TIMEZONE)
        body = self._start_now()

        self.assertEqual(body["state"], "forming")
        self.assertEqual(body["my_state"], "joined")
        row = self._row(body["id"])
        starts = datetime.combine(
            datetime.fromisoformat(row["on_date"]).date(),
            time.fromisoformat(row["start_time"]),
            tzinfo=APPLICATION_TIMEZONE,
        )
        deadline = datetime.fromisoformat(row["invite_expires_at"])
        # The database constraint is deadline <= start; a now group sits on it.
        self.assertEqual(deadline, starts)
        self.assertGreater(deadline, before)
        self.assertLessEqual(starts - before, timedelta(minutes=NOW_LEAD_MINUTES + 1))
        self.assertGreaterEqual(starts - before, timedelta(minutes=NOW_LEAD_MINUTES))

    def test_forming_group_is_open_to_others_without_its_spot_or_names(self) -> None:
        group_id = self._start_now()["id"]

        listed = self.client.get("/groups/open", headers=self.headers["s_second"]).json()

        self.assertEqual([g["id"] for g in listed], [group_id])
        self.assertEqual(listed[0]["area"], FORMING_AREA)
        self.assertEqual(listed[0]["seats_left"], 4)
        self.assertNotIn("The Nest", str(listed))
        self.assertNotIn("Founder", str(listed))

    def test_third_acceptance_confirms_and_everyone_sees_the_spot(self) -> None:
        group_id = self._start_now()["id"]

        second = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(self._row(group_id)["status"], "forming")

        third = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_third"])
        self.assertEqual(third.status_code, 200, third.text)
        self.assertEqual(self._row(group_id)["status"], "confirmed")
        self.assertIsNotNone(self._row(group_id)["confirmed_at"])

        for who in ("s_founder", "s_second", "s_third"):
            now = self.client.get("/me/now", headers=self.headers[who]).json()
            self.assertEqual(now["group"]["id"], group_id, who)
            self.assertEqual(now["group"]["my_state"], "joined")
            self.assertEqual(now["group"]["state"], "confirmed")
            self.assertEqual(now["group"]["spot"]["building"], "The Nest")

    def test_joining_twice_is_idempotent(self) -> None:
        group_id = self._start_now()["id"]
        self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])

        again = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])

        self.assertEqual(again.status_code, 200)
        rows = [
            m for m in self.database.tables["group_members"]
            if m["group_id"] == group_id and m["student_id"] == "s_second"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["invitation_status"], "accepted")

    def test_group_with_a_pending_invitation_is_not_open(self) -> None:
        group_id = self._start_now()["id"]
        self.database.tables["group_members"].append(
            {"group_id": group_id, "student_id": "s_fourth", "invitation_status": "invited", "arrived_at": None}
        )

        listed = self.client.get("/groups/open", headers=self.headers["s_second"]).json()
        joined = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])

        self.assertEqual(listed, [])
        self.assertEqual(joined.status_code, 404)

    def test_closed_invitations_hide_and_refuse_the_group(self) -> None:
        group_id = self._start_now()["id"]
        self._row(group_id)["invite_expires_at"] = (
            datetime.now(APPLICATION_TIMEZONE) - timedelta(minutes=1)
        ).isoformat()

        listed = self.client.get("/groups/open", headers=self.headers["s_second"]).json()
        joined = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])

        self.assertEqual(listed, [])
        self.assertEqual(joined.status_code, 404)
        self.assertFalse(any(
            m["student_id"] == "s_second" for m in self.database.tables["group_members"]
        ))

    def test_full_forming_group_refuses_another_member(self) -> None:
        group_id = self._start_now()["id"]
        # Four accepted members without confirming it, as a race would leave it.
        for index in range(4):
            self.database.tables["group_members"].append(
                {"group_id": group_id, "student_id": f"s_filler_{index}", "invitation_status": "accepted", "arrived_at": None}
            )
        self._row(group_id)["status"] = "forming"

        # Five accepted is confirmed by count, and confirmed with no seats left
        # is neither listed nor joinable.
        listed = self.client.get("/groups/open", headers=self.headers["s_second"]).json()
        joined = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])

        self.assertEqual(listed, [])
        self.assertEqual(joined.status_code, 409)

    def test_student_outside_the_gap_cannot_see_or_join(self) -> None:
        group_id = self._start_now()["id"]
        store.get("s_second").free_blocks = []

        listed = self.client.get("/groups/open", headers=self.headers["s_second"]).json()
        joined = self.client.post(f"/groups/{group_id}/join", headers=self.headers["s_second"])

        self.assertEqual(listed, [])
        self.assertEqual(joined.status_code, 404)

    def test_founder_without_a_free_block_still_sees_their_group(self) -> None:
        store.get("s_founder").free_blocks = []
        group_id = self._start_now()["id"]

        now = self.client.get("/me/now", headers=self.headers["s_founder"]).json()

        self.assertEqual(now["group"]["id"], group_id)
        self.assertEqual(now["group"]["needs"], 2)


if __name__ == "__main__":
    unittest.main()
