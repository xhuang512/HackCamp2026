import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

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
        self.assertEqual(
            response.json(),
            {
                "student_id": "s_demo_01",
                "first_name": "Maya",
                "session_token": "guest_demo_session",
                "is_guest": True,
            },
        )

    def test_create_student_validates_required_fields(self) -> None:
        response = self.client.post("/students", json={"first_name": "Maya"})

        self.assertEqual(response.status_code, 422)

    def test_now_returns_gap_and_pending_group(self) -> None:
        response = self.client.get("/me/now")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["gap"], {"day": "tue", "start": "13:00", "end": "15:00"})
        self.assertEqual(body["group"]["id"], "g_41")
        self.assertEqual(body["group"]["response"], "pending")
        self.assertEqual(body["group"]["spot"], {"building": "The Nest", "walk_min": 4})

    def test_join_returns_joined_response(self) -> None:
        response = self.client.post("/groups/g_41/join")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"group_id": "g_41", "response": "joined"})

    def test_skip_returns_skipped_response(self) -> None:
        response = self.client.post("/groups/g_41/skip")

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
        paths = self.client.get("/openapi.json").json()["paths"]

        self.assertTrue(
            {
                "/students",
                "/me/now",
                "/groups/{id}/join",
                "/groups/{id}/skip",
                "/projector",
                "/admin/reset",
            }.issubset(paths)
        )


if __name__ == "__main__":
    unittest.main()
