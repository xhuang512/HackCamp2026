import unittest
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient

from app.auth import create_guest_session
from app.db import get_db_client
from app.main import app
from tests.fakes import FakeSupabase


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

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
        self.database = FakeSupabase()
        app.dependency_overrides[get_db_client] = lambda: self.database
        self.session_token = create_guest_session("s_current")
        self.auth_headers = {"Authorization": f"Bearer {self.session_token}"}

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()

    def test_health_is_preserved(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_create_student_returns_guest_session(self) -> None:
        response = self.client.post(
            "/students",
            json={
                "first_name": "Maya",
                "tags": ["transfer"],
                "languages": ["English"],
                "courses": ["STAT 302"],
                "preset_schedule": "tue_thu_afternoon",
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["first_name"], "Maya")
        self.assertTrue(body["is_guest"])
        self.assertEqual(
            jwt.decode(
                body["session_token"],
                "test-only-secret-that-is-at-least-32-bytes",
                algorithms=["HS256"],
                issuer="hangout-api",
            )["sub"],
            body["student_id"],
        )
        persisted_blocks = [
            row
            for row in self.database.tables["free_blocks"]
            if row["student_id"] == body["student_id"]
        ]
        self.assertEqual(
            [(row["day"], row["start_time"], row["end_time"]) for row in persisted_blocks],
            [(1, "13:00", "15:00"), (3, "13:00", "15:00")],
        )

    def test_create_student_validates_required_fields(self) -> None:
        response = self.client.post("/students", json={"first_name": "Maya"})

        self.assertEqual(response.status_code, 422)

    def test_create_student_rejects_name_longer_than_database_limit(self) -> None:
        original_count = len(self.database.tables["students"])

        response = self.client.post(
            "/students",
            json={
                "first_name": "M" * 41,
                "preset_schedule": "tue_thu_afternoon",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.database.tables["students"]), original_count)

    def test_now_returns_gap_and_pending_group(self) -> None:
        response = self.client.get("/me/now", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["gap"],
            {"day": "tue", "start": "13:15", "end": "14:30"},
        )
        self.assertEqual(body["group"]["id"], "g_41")
        self.assertEqual(body["group"]["response"], "pending")
        self.assertEqual(body["group"]["members"], [])
        self.assertEqual(body["group"]["shared"], ["STAT 302", "Transfer student", "English"])
        self.assertEqual(
            body["group"]["spot"],
            {"building": "To be announced", "walk_min": 0},
        )

    def test_join_returns_joined_response(self) -> None:
        response = self.client.post("/groups/g_41/join", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"group_id": "g_41", "response": "joined"})
        current = next(
            row
            for row in self.database.tables["group_members"]
            if row["group_id"] == "g_41" and row["student_id"] == "s_current"
        )
        other = next(
            row
            for row in self.database.tables["group_members"]
            if row["group_id"] == "g_41" and row["student_id"] == "s_other"
        )
        self.assertEqual(current["invitation_status"], "accepted")
        self.assertEqual(other["invitation_status"], "accepted")

    def test_skip_returns_skipped_response(self) -> None:
        response = self.client.post("/groups/g_41/skip", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"group_id": "g_41", "response": "skipped"})

    def test_projector_returns_anonymous_counts(self) -> None:
        response = self.client.get("/projector")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"joined_count": 3, "group_count": 1})

    def test_admin_reset_returns_seed_counts(self) -> None:
        with patch.dict("os.environ", {"DEMO_MODE": "true"}, clear=True):
            response = self.client.post("/admin/reset")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"status": "reset", "seeded_students": 4, "seeded_groups": 1},
        )

    def test_admin_reset_is_disabled_outside_demo_mode(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            response = self.client.post("/admin/reset")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Demo reset is disabled"})

    def test_skeleton_endpoints_are_in_openapi(self) -> None:
        openapi = self.client.get("/openapi.json").json()
        paths = openapi["paths"]

        self.assertTrue(
            {
                "/students",
                "/options",
                "/me/now",
                "/groups/{id}/join",
                "/groups/{id}/skip",
                "/projector",
                "/admin/reset",
            }.issubset(paths)
        )
        suggested_group = openapi["components"]["schemas"]["SuggestedGroup"]
        self.assertTrue(
            {
                "status",
                "accepted_count",
                "minimum_required",
                "invite_expires_at",
            }.issubset(suggested_group["properties"])
        )


if __name__ == "__main__":
    unittest.main()
