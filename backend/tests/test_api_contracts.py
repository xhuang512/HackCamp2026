import unittest
from datetime import date, time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth, codes, config, demo, store
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
        self.session_token = create_guest_session("s_current")
        self.auth_headers = {"Authorization": f"Bearer {self.session_token}"}

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()

    def test_health_is_preserved(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_me_returns_the_private_profile(self) -> None:
        response = self.client.get("/me", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["onboarded"])
        self.assertTrue(response.json()["student"]["is_guest"])
        self.assertEqual(
            [badge["slug"] for badge in response.json()["badges"]],
            ["first_hello", "regular", "familiar_face"],
        )
        self.assertEqual(
            response.json()["badges"][1]["progress"],
            {"current": 0, "target": 3},
        )

    def test_create_student_returns_guest_session(self) -> None:
        response = self.client.post(
            "/students",
            json={
                "first_name": "Maya",
                "tags": ["transfer"],
                "languages": ["English"],
                "courses": ["STAT 302"],
                "preset_id": "tue-thu-afternoons",
                "guest": True,
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        student_id = body["student"]["id"]
        self.assertEqual(body["student"]["first_name"], "Maya")

        # The guest token is no longer a JWT. It is
        # `guest.<student_id>.<expiry>.<signature>`, signed over the id and
        # the expiry together, and it only verifies while that student
        # exists. read_guest_token is the one thing that should parse it.
        self.assertEqual(auth._read_guest_token(body["guest_token"]), student_id)

        persisted_blocks = [
            row
            for row in self.database.tables["free_blocks"]
            if row["student_id"] == student_id
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
                "preset_id": "tue-thu-afternoons",
                "guest": True,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(len(self.database.tables["students"]), original_count)

    def test_now_returns_gap_and_invited_group(self) -> None:
        response = self.client.get("/me/now", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            body["gap"],
            {"day": "tue", "start": "13:15", "end": "14:30"},
        )
        group = body["group"]
        self.assertEqual(group["id"], "g_41")
        self.assertEqual(group["my_state"], "invited")
        self.assertEqual(group["state"], "forming")
        self.assertEqual(group["members"], [])
        self.assertEqual(group["shared"], ["STAT 302", "Transfer student", "English"])
        # One joined member of two, so the group is two short of the minimum
        # and has no spot to show yet.
        self.assertEqual(group["joined_count"], 1)
        self.assertEqual(group["checked_in_count"], 0)
        self.assertEqual(group["needs"], 2)
        self.assertIsNone(group["spot"])

    def test_now_without_a_group_still_names_the_next_gap(self) -> None:
        self.database.tables["groups"] = []
        self.database.tables["group_members"] = []
        store.update(
            "s_current",
            free_blocks=[(1, time(13, 0), time(15, 0))],
        )

        response = self.client.get("/me/now", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "gap": {"day": "tue", "start": "13:00", "end": "15:00"},
                "group": None,
            },
        )

    def test_checkin_checks_both_students_in_once(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"
        other = codes.issue("s_other").code

        first = self.client.post(
            "/groups/g_41/checkin",
            json={"code": other},
            headers=self.auth_headers,
        )
        again = self.client.post(
            "/groups/g_41/checkin",
            json={"code": other},
            headers=self.auth_headers,
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["checked_in_count"], 2)
        self.assertEqual(first.json()["my_state"], "checked_in")
        self.assertTrue(first.json()["counted"])
        self.assertEqual(
            first.json()["new_badges"],
            [{"slug": "first_hello", "name": "First Hello"}],
        )
        # Scanning the same person twice changes nothing.
        self.assertEqual(again.json()["checked_in_count"], 2)
        self.assertFalse(again.json()["counted"])
        self.assertEqual(again.json()["new_badges"], [])

    def test_joined_caller_sees_top_badges_only_for_joined_members(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"
        self.database.tables["group_members"].extend(
            [
                {
                    "group_id": f"past-{index}",
                    "student_id": "s_other",
                    "invitation_status": "accepted",
                    "arrived_at": f"2026-10-{index + 1:02d}T12:00:00Z",
                }
                for index in range(3)
            ]
        )

        response = self.client.get("/groups/g_41", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["members"],
            [
                {"first_name": "Maya", "top_badge": None},
                {
                    "first_name": "Amir",
                    "top_badge": {"slug": "regular", "name": "Regular"},
                },
            ],
        )

    def test_checkin_rejects_a_code_from_outside_the_group(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"

        response = self.client.post(
            "/groups/g_41/checkin",
            json={"code": codes.issue("s_stranger").code},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            [m["arrived_at"] for m in self.database.tables["group_members"]],
            [None, None],
        )

    def test_checkin_explains_that_your_own_code_cannot_be_used(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"

        response = self.client.post(
            "/groups/g_41/checkin",
            json={"code": codes.issue("s_current").code},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Use a groupmate's code, not your own.")

    def test_typed_code_checks_a_groupmate_in(self) -> None:
        """The six-digit fallback, for a phone whose camera will not open."""
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"
        issued = codes.issue("s_other")
        self.assertEqual(len(issued.typed), 6)
        self.assertTrue(issued.typed.isdigit())

        response = self.client.post(
            "/groups/g_41/checkin",
            # Spaced the way the screen prints it and a student would type it.
            json={"code": f"{issued.typed[:3]} {issued.typed[3:]}"},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checked_in_count"], 2)
        self.assertEqual(response.json()["my_state"], "checked_in")

    def test_typed_code_from_outside_the_group_is_rejected(self) -> None:
        """The member list is the whole search space, so a stranger's six
        digits have nothing to match against even when they are genuine."""
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"

        response = self.client.post(
            "/groups/g_41/checkin",
            json={"code": codes.issue("s_stranger").typed},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            [m["arrived_at"] for m in self.database.tables["group_members"]],
            [None, None],
        )

    def test_a_wrong_six_digit_code_is_rejected(self) -> None:
        for membership in self.database.tables["group_members"]:
            membership["invitation_status"] = "accepted"
        wrong = f"{(int(codes.issue('s_other').typed) + 1) % 1000000:06d}"

        response = self.client.post(
            "/groups/g_41/checkin",
            json={"code": wrong},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 422)

    def test_typed_code_is_not_a_slice_of_the_qr_signature(self) -> None:
        """Reading one form off a screen must not hand over the other."""
        issued = codes.issue("s_other")
        signature = issued.code.rsplit(".", 1)[1]
        self.assertNotIn(issued.typed, signature)

    def test_checkin_code_needs_a_joined_membership(self) -> None:
        response = self.client.get(
            "/groups/g_41/checkin-code", headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 403)

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

    def test_join_open_group_creates_a_membership(self) -> None:
        store.get("s_current").free_blocks = [(1, time(13, 0), time(15, 0))]
        self.database.tables["group_members"] = [
            row for row in self.database.tables["group_members"]
            if row["student_id"] != "s_current"
        ]
        self.database.tables["groups"][0]["status"] = "confirmed"
        for index in range(2):
            student_id = f"s_open_{index}"
            self.database.tables["students"].append(
                {"id": student_id, "first_name": f"Open {index}", "paused": False, "deleted_at": None}
            )
            self.database.tables["group_members"].append(
                {
                    "group_id": "g_41",
                    "student_id": student_id,
                    "invitation_status": "accepted",
                    "arrived_at": None,
                }
            )

        response = self.client.post("/groups/g_41/join", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(
            row["group_id"] == "g_41"
            and row["student_id"] == "s_current"
            and row["invitation_status"] == "accepted"
            for row in self.database.tables["group_members"]
        ))

    def test_open_groups_are_anonymous_and_joinable(self) -> None:
        store.get("s_current").free_blocks = [(1, time(13, 0), time(15, 0))]
        self.database.tables["group_members"] = [
            row for row in self.database.tables["group_members"]
            if row["student_id"] != "s_current"
        ]
        self.database.tables["groups"][0]["status"] = "confirmed"
        for index in range(2):
            student_id = f"s_listing_{index}"
            self.database.tables["students"].append(
                {"id": student_id, "first_name": f"Hidden {index}", "paused": False, "deleted_at": None}
            )
            self.database.tables["group_members"].append(
                {
                    "group_id": "g_41",
                    "student_id": student_id,
                    "invitation_status": "accepted",
                    "arrived_at": None,
                }
            )

        response = self.client.get("/groups/open", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertNotIn("members", response.text)
        self.assertNotIn("Hidden", response.text)

    def test_start_group_creates_a_joined_founder(self) -> None:
        store.get("s_current").free_blocks = [(1, time(13, 0), time(15, 0))]

        response = self.client.post(
            "/groups",
            json={"building": "nest", "mode": "social", "now": False},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["state"], "forming")
        self.assertEqual(body["my_state"], "joined")
        self.assertIsNone(body["spot"])

    def test_skip_returns_skipped_response(self) -> None:
        response = self.client.post("/groups/g_41/skip", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"group_id": "g_41", "response": "skipped"})

    def test_projector_returns_anonymous_counts(self) -> None:
        response = self.client.get("/projector")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        # Counts and places only. Nothing in this payload identifies anyone,
        # which is what lets the route stay public.
        self.assertEqual(
            set(body),
            {"forming", "confirmed", "checked_in", "students", "dots"},
        )
        self.assertEqual(body["checked_in"], 0)
        self.assertNotIn("first_name", response.text)

    def test_map_hides_buildings_under_the_minimum(self) -> None:
        response = self.client.get("/map", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        # Two students at The Nest, and the floor is three, so the building
        # is absent rather than shown with a small number on it.
        self.assertEqual(response.json(), {"buildings": [], "my_group": None})

    def test_map_shows_a_building_once_three_students_are_there(self) -> None:
        # The map answers "what is happening right now", so it only reads
        # today's groups. The seed group sits on the next Tuesday.
        self.database.tables["groups"][0]["on_date"] = date.today().isoformat()
        self.database.tables["students"].append(
            {"id": "s_third", "first_name": "Rosa", "paused": False, "deleted_at": None}
        )
        self.database.tables["group_members"].append(
            {
                "group_id": "g_41",
                "student_id": "s_third",
                "response": "joined",
                "arrived_at": None,
            }
        )

        response = self.client.get("/map", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        buildings = response.json()["buildings"]
        self.assertEqual(len(buildings), 1)
        self.assertEqual(buildings[0]["slug"], "nest")
        self.assertEqual(buildings[0]["free_count"], 3)

    def test_map_withholds_my_pin_from_an_invited_caller(self) -> None:
        # A genuinely confirmed group, three others accepted, and the caller
        # still only invited. The pin carries the building's coordinates, so
        # handing it over would say where the group is meeting before the
        # caller joined it, which the group card already refuses to do.
        #
        # The building itself may well appear in the public activity list:
        # that is a count with no name on it and no claim about the caller.
        # Only my_group is personal, so only my_group is withheld.
        self.database.tables["groups"][0]["on_date"] = date.today().isoformat()
        self.database.tables["groups"][0]["status"] = "confirmed"
        for student_id in ("s_third", "s_fourth"):
            self.database.tables["students"].append(
                {
                    "id": student_id,
                    "first_name": "Rosa",
                    "paused": False,
                    "deleted_at": None,
                }
            )
            self.database.tables["group_members"].append(
                {
                    "group_id": "g_41",
                    "student_id": student_id,
                    "invitation_status": "accepted",
                    "arrived_at": None,
                }
            )
        self.assertEqual(self._membership("s_current")["invitation_status"], "invited")

        response = self.client.get("/map", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["my_group"])

    def test_map_keeps_my_pin_once_the_group_is_active(self) -> None:
        # A group that has started is exactly when its member needs the pin.
        # This read used to require the status to be "confirmed" and nothing
        # else, so the pin vanished the moment the meeting began.
        self.database.tables["groups"][0]["on_date"] = date.today().isoformat()
        self.database.tables["groups"][0]["status"] = "active"
        self._membership("s_current")["invitation_status"] = "accepted"

        response = self.client.get("/map", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        pin = response.json()["my_group"]
        self.assertIsNotNone(pin)
        self.assertEqual(pin["slug"], "nest")
        self.assertEqual(pin["group_id"], "g_41")

    def _membership(self, student_id: str) -> dict[str, object]:
        return next(
            row
            for row in self.database.tables["group_members"]
            if row["student_id"] == student_id
        )

    def test_patch_me_reaches_the_table_the_matcher_reads(self) -> None:
        response = self.client.patch(
            "/me", json={"paused": True}, headers=self.auth_headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["paused"])
        # The point of the mirror write: pause is a matching rule, and the
        # matcher reads this row, not the in-memory one.
        current = next(
            row for row in self.database.tables["students"] if row["id"] == "s_current"
        )
        self.assertTrue(current["paused"])

    def test_admin_reset_recreates_the_seed(self) -> None:
        with patch.object(config, "DEMO_MODE", True):
            response = self.client.post("/admin/reset")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "reset")
        self.assertEqual(body["seeded_buildings"], len(demo.BUILDINGS))
        # It actually writes now. The old route returned fixed numbers and
        # changed nothing, so step 6 of the demo check could not pass.
        self.assertGreater(body["seeded_students"], 0)
        self.assertEqual(
            len([row for row in self.database.tables["students"] if row.get("is_seed")]),
            body["seeded_students"],
        )

    def test_admin_reset_is_disabled_outside_demo_mode(self) -> None:
        with patch.object(config, "DEMO_MODE", False):
            response = self.client.post("/admin/reset")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Demo reset is disabled"})

    def test_skeleton_endpoints_are_in_openapi(self) -> None:
        openapi = self.client.get("/openapi.json").json()
        paths = openapi["paths"]

        self.assertTrue(
            {
                "/me",
                "/students",
                "/options",
                "/me/now",
                "/map",
                "/groups",
                "/groups/open",
                "/groups/{id}",
                "/groups/{id}/join",
                "/groups/{id}/skip",
                "/groups/{id}/checkin-code",
                "/groups/{id}/checkin",
                "/projector",
                "/admin/reset",
            }.issubset(paths)
        )
        suggested_group = openapi["components"]["schemas"]["GroupOut"]
        self.assertTrue(
            {
                "state",
                "my_state",
                "joined_count",
                "checked_in_count",
                "needs",
            }.issubset(suggested_group["properties"])
        )


if __name__ == "__main__":
    unittest.main()
