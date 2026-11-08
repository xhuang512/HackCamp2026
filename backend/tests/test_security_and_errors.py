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

    def test_authenticated_student_without_suggestion_gets_a_null_group(self) -> None:
        self.database.tables["groups"] = []
        self.database.tables["group_members"] = []
        token = create_guest_session("s_current")

        response = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        # The contract shape: one response with a null group, not a second
        # top-level shape the frontend has to branch on.
        self.assertIsNone(response.json()["group"])

    def test_declined_student_gets_a_null_group(self) -> None:
        self.database.tables["group_members"][0]["invitation_status"] = "declined"
        token = create_guest_session("s_current")

        response = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["group"])

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
            {
                row["student_id"]: row["invitation_status"]
                for row in self.database.tables["group_members"]
            },
            {"s_current": "invited", "s_other": "accepted"},
        )

    def test_confirmed_group_shows_first_names_and_the_spot(self) -> None:
        # A third member, because a group confirms at MIN_GROUP_SIZE joined
        # and that is the moment the spot appears.
        self.database.tables["students"].append(
            {"id": "s_third", "first_name": "Rosa", "paused": False, "deleted_at": None}
        )
        self.database.tables["group_members"].append(
            {
                "group_id": "g_41",
                "student_id": "s_third",
                "invitation_status": "accepted",
                "arrived_at": None,
            }
        )
        token = create_guest_session("s_current")
        headers = {"Authorization": f"Bearer {token}"}

        joined = self.client.post("/groups/g_41/join", headers=headers)
        suggestion = self.client.get("/me/now", headers=headers)

        self.assertEqual(joined.status_code, 200)
        self.assertEqual(suggestion.status_code, 200)
        group = suggestion.json()["group"]
        self.assertEqual(group["state"], "confirmed")
        self.assertEqual(
            sorted(member["first_name"] for member in group["members"]),
            ["Amir", "Maya", "Rosa"],
        )
        self.assertEqual(group["spot"]["building"], "The Nest")

    def test_forming_group_keeps_the_meeting_spot_private(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = (
                "accepted"
                if membership["student_id"] == "s_current"
                else "declined"
            )
        token = create_guest_session("s_current")

        suggestion = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        self.assertEqual(suggestion.status_code, 200)
        group = suggestion.json()["group"]
        self.assertEqual(group["state"], "forming")
        self.assertEqual(
            group["members"],
            [{"first_name": "Maya", "top_badge": None}],
        )
        self.assertIsNone(group["spot"])

    def test_an_invited_member_is_counted_but_not_named(self) -> None:
        # s_other has joined, s_current has not answered. A joiner sees the
        # names of people who joined, never of people merely invited.
        self.database.tables["group_members"][0]["invitation_status"] = "accepted"
        self.database.tables["group_members"][1]["invitation_status"] = "invited"
        token = create_guest_session("s_current")

        suggestion = self.client.get(
            "/me/now",
            headers={"Authorization": f"Bearer {token}"},
        )

        group = suggestion.json()["group"]
        self.assertEqual(
            group["members"],
            [{"first_name": "Maya", "top_badge": None}],
        )
        self.assertEqual(group["joined_count"], 1)
        self.assertNotIn("Amir", suggestion.text)

    def test_a_non_member_cannot_read_a_group(self) -> None:
        store.put(
            store.Student(
                id="outsider",
                first_name="Outsider",
                auth_sub="guest:outsider",
                is_guest=True,
            )
        )
        token = create_guest_session("outsider")

        response = self.client.get(
            "/groups/g_41",
            headers={"Authorization": f"Bearer {token}"},
        )

        # 404, not 403: a stranger should not learn that the group exists.
        self.assertEqual(response.status_code, 404)

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
