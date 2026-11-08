import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import store
from app.auth import create_guest_session
from app.db import DatabaseConfigurationError, create_supabase_client, get_db_client
from app.main import app
from tests.fakes import FakeSupabase


class SecurityAndErrorTests(unittest.TestCase):
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
        store.reset()
        store.put(
            store.Student(
                id="s_current",
                first_name="Current",
                auth_sub="guest:s_current",
                is_guest=True,
            )
        )
        self.database = FakeSupabase()
        app.dependency_overrides[get_db_client] = lambda: self.database
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()
        create_supabase_client.cache_clear()

    def test_private_endpoint_requires_guest_session(self) -> None:
        response = self.client.get("/me/now")

        self.assertEqual(response.status_code, 401)
        # Wording comes from the merged auth module, which answers every
        # unauthenticated call the same way.
        self.assertEqual(response.json(), {"detail": "Sign in to do that."})

    def test_authenticated_student_without_suggestion_gets_waiting_state(self) -> None:
        self.database.tables["groups"] = []
        self.database.tables["group_members"] = []
        token = create_guest_session("s_current")

        response = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "waiting"})

    def test_skipped_student_gets_waiting_state(self) -> None:
        self.database.tables["group_members"][0]["response"] = "skipped"
        token = create_guest_session("s_current")

        response = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "waiting"})

    def test_tampered_guest_session_is_rejected(self) -> None:
        token = create_guest_session("s_current")
        response = self.client.post(
            "/groups/g_41/join",
            headers={"Authorization": f"Bearer {token}tampered"},
        )

        self.assertEqual(response.status_code, 401)

    def test_unknown_preset_does_not_create_student(self) -> None:
        original_count = len(self.database.tables["students"])
        response = self.client.post(
            "/students",
            json={"first_name": "Maya", "preset_schedule": "not-a-preset"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.database.tables["students"]), original_count)

    def test_membership_for_another_student_cannot_be_updated(self) -> None:
        # A real signed-in student who is simply not in this group. The point
        # is the 404 from the membership check, so the student has to exist:
        # an unknown id now stops at the token check with a 401 and never
        # reaches the router.
        store.put(
            store.Student(
                id="not-a-member",
                first_name="Other",
                auth_sub="guest:not-a-member",
                is_guest=True,
            )
        )
        token = create_guest_session("not-a-member")
        response = self.client.post(
            "/groups/g_41/skip",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            {row["student_id"]: row["response"] for row in self.database.tables["group_members"]},
            {"s_current": "pending", "s_other": "joined"},
        )

    def test_joined_student_can_see_group_first_names(self) -> None:
        token = create_guest_session("s_current")
        headers = {"Authorization": f"Bearer {token}"}
        joined = self.client.post("/groups/g_41/join", headers=headers)
        suggestion = self.client.get("/me/now", headers=headers)

        self.assertEqual(joined.status_code, 200)
        self.assertEqual(suggestion.status_code, 200)
        self.assertEqual(suggestion.json()["group"]["members"], ["Maya", "Amir"])
        self.assertEqual(
            suggestion.json()["group"]["spot"],
            {"building": "The Nest", "walk_min": 0},
        )

    def test_skipped_member_keeps_meeting_spot_private(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["response"] = (
                "joined" if membership["student_id"] == "s_current" else "skipped"
            )
        token = create_guest_session("s_current")

        suggestion = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(suggestion.status_code, 200)
        self.assertEqual(suggestion.json()["group"]["members"], ["Maya"])
        self.assertEqual(
            suggestion.json()["group"]["spot"],
            {"building": "To be announced", "walk_min": 0},
        )

    def test_missing_supabase_configuration_is_clear(self) -> None:
        create_supabase_client.cache_clear()
        with (
            patch("app.db.ROOT_ENV_FILE", "/definitely/missing/.env"),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(
                DatabaseConfigurationError,
                "SUPABASE_URL, SUPABASE_SERVICE_KEY",
            ),
        ):
            create_supabase_client()
