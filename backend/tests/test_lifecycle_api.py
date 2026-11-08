import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import create_guest_session
from app.db import get_db_client
from app.main import app
from app.repositories import RepositoryError
from app.repositories.group_members import GroupMemberRepository
from tests.fakes import FakePostgrestError, FakeSupabase, seed_tables


class LifecycleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            "os.environ",
            {
                "GUEST_SESSION_SECRET": "test-only-secret-that-is-at-least-32-bytes",
                "CURRENT_TERM": "2026W1",
            },
            clear=True,
        )
        self.environment.start()
        self.database = FakeSupabase(self._lifecycle_tables())
        app.dependency_overrides[get_db_client] = lambda: self.database
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()

    def test_third_acceptance_atomically_confirms_group(self) -> None:
        response = self._post_as("s_current", "/groups/g_41/join")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"group_id": "g_41", "response": "joined"})
        group = self.database.tables["groups"][0]
        self.assertEqual(group["status"], "confirmed")
        self.assertIsNotNone(group["confirmed_at"])
        self.assertEqual(self._accepted_count(), 3)

    def test_location_hidden_before_three_acceptances(self) -> None:
        self._membership("s_current")["invitation_status"] = "accepted"
        self._membership("s3")["invitation_status"] = "invited"

        response = self._get_now("s_current")

        self.assertEqual(response.status_code, 200)
        group = response.json()["group"]
        self.assertEqual(group["status"], "forming")
        self.assertEqual(group["accepted_count"], 2)
        self.assertEqual(group["minimum_required"], 3)
        self.assertEqual(group["members"], ["Maya", "Amir"])
        self.assertEqual(
            group["spot"],
            {"building": "To be announced", "walk_min": 0},
        )

    def test_accepted_member_sees_location_after_confirmation(self) -> None:
        joined = self._post_as("s_current", "/groups/g_41/join")
        self.assertEqual(joined.status_code, 200)

        response = self._get_now("s_current")

        group = response.json()["group"]
        self.assertEqual(group["status"], "confirmed")
        self.assertEqual(group["accepted_count"], 3)
        self.assertEqual(group["members"], ["Maya", "Amir", "Rosa"])
        self.assertEqual(
            group["spot"],
            {"building": "The Nest", "walk_min": 0},
        )
        self.assertIn("invite_expires_at", group)

    def test_remaining_invited_member_cannot_see_names_or_location(self) -> None:
        self._membership("s_current")["invitation_status"] = "accepted"
        self.database.tables["groups"][0]["status"] = "confirmed"
        self.database.tables["groups"][0]["confirmed_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        response = self._get_now("s4")

        self.assertEqual(response.status_code, 200)
        group = response.json()["group"]
        self.assertEqual(group["response"], "pending")
        self.assertEqual(group["accepted_count"], 3)
        self.assertEqual(group["members"], [])
        self.assertEqual(
            group["spot"],
            {"building": "To be announced", "walk_min": 0},
        )

    def test_accepted_member_cannot_skip(self) -> None:
        self._membership("s_current")["invitation_status"] = "accepted"

        response = self._post_as("s_current", "/groups/g_41/skip")

        self.assertEqual(response.status_code, 409)
        self.assertIn("accepted invitation", response.json()["detail"])

    def test_declined_or_expired_invitation_cannot_be_accepted(self) -> None:
        for invitation_status in ("declined", "expired"):
            with self.subTest(invitation_status=invitation_status):
                self._membership("s_current")["invitation_status"] = invitation_status

                response = self._post_as("s_current", "/groups/g_41/join")

                self.assertEqual(response.status_code, 409)
                self.assertIn(
                    f"{invitation_status} invitation",
                    response.json()["detail"],
                )

    def test_expired_invitation_cannot_be_skipped(self) -> None:
        self._membership("s_current")["invitation_status"] = "expired"

        response = self._post_as("s_current", "/groups/g_41/skip")

        self.assertEqual(response.status_code, 409)

    def test_student_without_membership_cannot_respond(self) -> None:
        response = self._post_as("not-a-member", "/groups/g_41/join")

        self.assertEqual(response.status_code, 404)
        self.assertIn("No membership exists", response.json()["detail"])

    def test_active_group_rejects_a_new_invitation_response(self) -> None:
        self.database.tables["groups"][0]["status"] = "active"

        response = self._post_as("s_current", "/groups/g_41/join")

        self.assertEqual(response.status_code, 409)
        self.assertIn("group is active", response.json()["detail"])

    def test_deadline_rejects_new_response_and_now_returns_waiting(self) -> None:
        self.database.tables["groups"][0]["invite_expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()

        joined = self._post_as("s_current", "/groups/g_41/join")
        suggestion = self._get_now("s_current")

        self.assertEqual(joined.status_code, 409)
        self.assertEqual(suggestion.status_code, 200)
        self.assertEqual(suggestion.json(), {"status": "waiting"})

    def test_repeated_join_and_skip_are_idempotent(self) -> None:
        first_join = self._post_as("s_current", "/groups/g_41/join")
        second_join = self._post_as("s_current", "/groups/g_41/join")
        self.assertEqual(first_join.status_code, 200)
        self.assertEqual(second_join.status_code, 200)
        self.assertEqual(self._accepted_count(), 3)

        self._membership("s4")["invitation_status"] = "invited"
        first_skip = self._post_as("s4", "/groups/g_41/skip")
        second_skip = self._post_as("s4", "/groups/g_41/skip")
        self.assertEqual(first_skip.status_code, 200)
        self.assertEqual(second_skip.status_code, 200)
        self.assertEqual(self._membership("s4")["invitation_status"], "declined")

    def test_authentication_waiting_and_database_errors_remain_distinct(self) -> None:
        unauthenticated = self.client.post("/groups/g_41/join")
        self.assertEqual(unauthenticated.status_code, 401)

        self.database.tables["groups"] = []
        self.database.tables["group_members"] = []
        waiting = self._get_now("s_current")
        self.assertEqual(waiting.status_code, 200)
        self.assertEqual(waiting.json(), {"status": "waiting"})

        self.database = FakeSupabase(self._lifecycle_tables())
        app.dependency_overrides[get_db_client] = lambda: self.database
        with patch.object(self.database, "rpc", side_effect=RuntimeError("offline")):
            database_error = self._post_as("s_current", "/groups/g_41/join")
        self.assertEqual(database_error.status_code, 502)
        self.assertEqual(
            database_error.json(),
            {"detail": "Could not update group membership"},
        )

        with patch.object(
            GroupMemberRepository,
            "list_for_student",
            side_effect=RepositoryError("offline"),
        ):
            suggestion_error = self._get_now("s_current")
        self.assertEqual(suggestion_error.status_code, 502)
        self.assertEqual(
            suggestion_error.json(),
            {"detail": "Could not load the current group suggestion"},
        )

    def test_malformed_group_id_is_not_reported_as_a_database_outage(self) -> None:
        with patch.object(
            self.database,
            "rpc",
            side_effect=FakePostgrestError("22P02", "invalid input syntax for uuid"),
        ):
            response = self._post_as("s_current", "/groups/not-a-uuid/join")

        self.assertEqual(response.status_code, 404)

    def _post_as(self, student_id: str, path: str):
        return self.client.post(path, headers=self._headers(student_id))

    def _get_now(self, student_id: str):
        return self.client.get("/me/now", headers=self._headers(student_id))

    @staticmethod
    def _headers(student_id: str) -> dict[str, str]:
        token = create_guest_session(student_id)
        return {"Authorization": f"Bearer {token}"}

    def _membership(self, student_id: str) -> dict[str, object]:
        return next(
            row
            for row in self.database.tables["group_members"]
            if row["student_id"] == student_id
        )

    def _accepted_count(self) -> int:
        return sum(
            row["invitation_status"] == "accepted"
            for row in self.database.tables["group_members"]
        )

    @staticmethod
    def _lifecycle_tables() -> dict[str, list[dict[str, object]]]:
        tables = seed_tables()
        tables["students"].extend(
            [
                {
                    "id": "s3",
                    "first_name": "Rosa",
                    "paused": False,
                    "deleted_at": None,
                },
                {
                    "id": "s4",
                    "first_name": "Ji-woo",
                    "paused": False,
                    "deleted_at": None,
                },
            ]
        )
        for index, student_id in enumerate(("s_other", "s3", "s4"), start=2):
            tables["free_blocks"].append(
                {
                    "id": index,
                    "student_id": student_id,
                    "day": 1,
                    "start_time": "13:00:00",
                    "end_time": "15:00:00",
                }
            )
        group = tables["groups"][0]
        group["status"] = "forming"
        group["invite_expires_at"] = (
            datetime.now(timezone.utc) + timedelta(days=1)
        ).isoformat()
        group["confirmed_at"] = None
        group["status_changed_at"] = datetime.now(timezone.utc).isoformat()
        tables["group_members"] = [
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
            {
                "group_id": "g_41",
                "student_id": "s3",
                "invitation_status": "accepted",
                "arrived_at": None,
            },
            {
                "group_id": "g_41",
                "student_id": "s4",
                "invitation_status": "invited",
                "arrived_at": None,
            },
        ]
        return tables


if __name__ == "__main__":
    unittest.main()
