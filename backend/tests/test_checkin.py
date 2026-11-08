from __future__ import annotations

import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import codes, store
from app.auth import create_guest_session
from app.db import get_db_client
from app.main import app
from app.routers.groups import get_checkin_now
from app.timezones import APPLICATION_TIMEZONE
from tests.fakes import FakeSupabase, seed_tables


TEST_SECRET = "check-in-tests-use-a-secret-longer-than-32-bytes"


class CheckInCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            "os.environ", {"GUEST_SESSION_SECRET": TEST_SECRET}, clear=True
        )
        self.environment.start()
        self.now = 1_800_000_015.0

    def tearDown(self) -> None:
        self.environment.stop()

    def test_valid_code_and_previous_rotation_window(self) -> None:
        current = codes.issue("student-1", now=self.now)
        previous = codes.issue(
            "student-1", now=self.now - codes.CHECKIN_WINDOW_SECONDS
        )

        self.assertEqual(codes.read(current.code, now=self.now), "student-1")
        self.assertEqual(codes.read(previous.code, now=self.now), "student-1")
        self.assertGreaterEqual(current.expires_in, 1)
        self.assertLessEqual(current.expires_in, codes.CHECKIN_WINDOW_SECONDS)

    def test_modified_signature_and_invalid_payload_are_rejected(self) -> None:
        issued = codes.issue("student-1", now=self.now)
        replacement = "0" if issued.code[-1] != "0" else "1"
        tampered = f"{issued.code[:-1]}{replacement}"

        self.assertIsNone(codes.read(tampered, now=self.now))
        for invalid in ("", "hc1", "hc1.student.bad.signature", "hc2.a.1.sig"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(codes.read(invalid, now=self.now))

    def test_expired_and_future_windows_are_rejected(self) -> None:
        expired = codes.issue(
            "student-1", now=self.now - 2 * codes.CHECKIN_WINDOW_SECONDS
        )
        future = codes.issue(
            "student-1", now=self.now + codes.CHECKIN_WINDOW_SECONDS
        )

        self.assertIsNone(codes.read(expired.code, now=self.now))
        self.assertIsNone(codes.read(future.code, now=self.now))

    def test_missing_or_short_secret_is_rejected(self) -> None:
        for environment in ({}, {"GUEST_SESSION_SECRET": "too-short"}):
            with (
                self.subTest(environment=environment),
                patch.dict("os.environ", environment, clear=True),
                patch("app.codes.load_dotenv"),
                self.assertRaises(codes.CheckInCodeConfigurationError),
            ):
                codes.issue("student-1", now=self.now)


class CheckInApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            "os.environ",
            {
                "GUEST_SESSION_SECRET": TEST_SECRET,
                "CURRENT_TERM": "2026W1",
            },
            clear=True,
        )
        self.environment.start()
        self.now = datetime(2026, 11, 10, 13, 30, tzinfo=APPLICATION_TIMEZONE)
        self.database = FakeSupabase(self._tables())
        store.reset()
        for row in self.database.tables["students"]:
            student_id = str(row["id"])
            store.put(
                store.Student(
                    id=student_id,
                    first_name=str(row["first_name"]),
                    auth_sub=f"guest:{student_id}",
                    is_guest=True,
                )
            )
        app.dependency_overrides[get_db_client] = lambda: self.database
        app.dependency_overrides[get_checkin_now] = lambda: self.now
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        store.reset()
        self.environment.stop()

    def test_code_generation_requires_authentication_and_accepted_membership(self) -> None:
        unauthenticated = self.client.get("/groups/g_41/checkin-code")
        accepted = self._get_code("s_current")
        invited = self._get_code("s_invited")
        nonmember = self._get_code("s_outside")

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertTrue(accepted.json()["code"].startswith("hc1.s_current."))
        self.assertEqual(accepted.json()["joined_count"], 3)
        self.assertEqual(accepted.json()["checked_in_count"], 0)
        self.assertEqual(accepted.json()["my_state"], "joined")
        self.assertEqual(invited.status_code, 403)
        self.assertEqual(nonmember.status_code, 404)

    def test_checkin_requires_authentication(self) -> None:
        response = self.client.post(
            "/groups/g_41/checkin", json={"code": self._code("s_other")}
        )
        self.assertEqual(response.status_code, 401)

    def test_success_checks_in_both_members_and_advances_group(self) -> None:
        response = self._scan("s_current", self._code("s_other"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "joined_count": 3,
                "checked_in_count": 2,
                "my_state": "checked_in",
                "counted": True,
                "new_badges": [{"slug": "first_hello", "name": "First Hello"}],
            },
        )
        self.assertEqual(self._group()["status"], "active")
        self.assertEqual(self._member("s_current")["arrived_at"], self.now.isoformat())
        self.assertEqual(self._member("s_other")["arrived_at"], self.now.isoformat())
        self.assertIsNone(self._member("s_third")["arrived_at"])
        progress = self._get_code("s_other").json()
        self.assertEqual(progress["checked_in_count"], 2)
        self.assertEqual(progress["my_state"], "checked_in")

    def test_repeated_scan_is_idempotent_and_preserves_timestamps(self) -> None:
        first = self._scan("s_current", self._code("s_other"))
        first_timestamp = self._member("s_current")["arrived_at"]
        self.now += timedelta(minutes=1)
        second = self._scan("s_current", self._code("s_other"))

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["counted"])
        self.assertEqual(self._member("s_current")["arrived_at"], first_timestamp)
        self.assertEqual(self._member("s_other")["arrived_at"], first_timestamp)

    def test_badges_are_awarded_once_per_verified_checkin(self) -> None:
        first = self._scan("s_current", self._code("s_other"))
        repeat = self._scan("s_current", self._code("s_other"))
        # The presenter was checked in by the first scan, so scanning back
        # changes nothing for them either.
        reverse = self._scan("s_other", self._code("s_current"))

        self.assertEqual(
            [b["slug"] for b in first.json()["new_badges"]], ["first_hello"]
        )
        self.assertEqual(repeat.json()["new_badges"], [])
        self.assertEqual(reverse.json()["new_badges"], [])

        me = self.client.get("/me", headers=self._headers("s_current")).json()
        self.assertEqual(
            [(b["slug"], b["earned"], b["progress"]) for b in me["badges"]],
            [
                ("first_hello", True, {"current": 1, "target": 1}),
                ("regular", False, {"current": 1, "target": 3}),
                ("familiar_face", False, {"current": 1, "target": 5}),
            ],
        )
        self.assertTrue(all(b["description"] for b in me["badges"]))

    def test_me_has_locked_badges_before_any_checkin(self) -> None:
        me = self.client.get("/me", headers=self._headers("s_current")).json()

        self.assertEqual(len(me["badges"]), 3)
        self.assertFalse(any(b["earned"] for b in me["badges"]))

    def test_invalid_self_wrong_group_and_unaccepted_codes_are_rejected(self) -> None:
        invalid = self._scan("s_current", "not-a-code")
        own = self._scan("s_current", self._code("s_current"))
        wrong_group = self._scan("s_current", self._code("s_outside"))
        invited = self._scan("s_current", self._code("s_invited"))

        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(own.status_code, 422)
        self.assertEqual(wrong_group.status_code, 422)
        self.assertEqual(invited.status_code, 409)
        self.assertTrue(
            all(member["arrived_at"] is None for member in self.database.tables["group_members"])
        )

    def test_lifecycle_and_meeting_time_boundaries(self) -> None:
        for group_status in ("forming", "completed", "dissolved"):
            with self.subTest(group_status=group_status):
                self._group()["status"] = group_status
                response = self._get_code("s_current")
                self.assertEqual(response.status_code, 409)

        self._group()["status"] = "confirmed"
        self.now = datetime(2026, 11, 10, 12, 59, 59, tzinfo=APPLICATION_TIMEZONE)
        self.assertEqual(self._get_code("s_current").status_code, 409)

        self.now = datetime(2026, 11, 10, 13, 0, tzinfo=APPLICATION_TIMEZONE)
        self.assertEqual(self._get_code("s_current").status_code, 200)

        self.now = datetime(2026, 11, 10, 13, 59, 59, tzinfo=APPLICATION_TIMEZONE)
        self.assertEqual(self._get_code("s_current").status_code, 200)

        self.now = datetime(2026, 11, 10, 14, 0, tzinfo=APPLICATION_TIMEZONE)
        self.assertEqual(self._get_code("s_current").status_code, 409)

        self._group()["status"] = "active"
        self.now = datetime(2026, 11, 10, 13, 30, tzinfo=APPLICATION_TIMEZONE)
        self.assertEqual(self._get_code("s_current").status_code, 200)

    def test_failed_database_write_returns_502_without_partial_attendance(self) -> None:
        with patch.object(self.database, "rpc", side_effect=RuntimeError("offline")):
            response = self._scan("s_current", self._code("s_other"))

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "Could not record meetup check-in"})
        self.assertIsNone(self._member("s_current")["arrived_at"])
        self.assertIsNone(self._member("s_other")["arrived_at"])

    def test_endpoints_are_documented_in_openapi(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/groups/{id}/checkin-code", paths)
        self.assertIn("/groups/{id}/checkin", paths)

    def _get_code(self, student_id: str):
        return self.client.get(
            "/groups/g_41/checkin-code", headers=self._headers(student_id)
        )

    def _scan(self, student_id: str, code: str):
        return self.client.post(
            "/groups/g_41/checkin",
            json={"code": code},
            headers=self._headers(student_id),
        )

    def _code(self, student_id: str) -> str:
        return codes.issue(student_id, now=self.now.timestamp()).code

    @staticmethod
    def _headers(student_id: str) -> dict[str, str]:
        token = create_guest_session(student_id)
        return {"Authorization": f"Bearer {token}"}

    def _group(self) -> dict:
        return self.database.tables["groups"][0]

    def _member(self, student_id: str) -> dict:
        return next(
            member
            for member in self.database.tables["group_members"]
            if member["student_id"] == student_id
        )

    def _tables(self) -> dict[str, list[dict]]:
        tables = deepcopy(seed_tables())
        tables["groups"][0].update(
            {
                "on_date": "2026-11-10",
                "start_time": "13:00:00",
                "end_time": "14:00:00",
                "status": "confirmed",
                "invite_expires_at": (
                    self.now.replace(hour=13, minute=0) - timedelta(minutes=10)
                ).isoformat(),
                "confirmed_at": self.now.replace(hour=12, minute=55).isoformat(),
            }
        )
        tables["students"].extend(
            [
                {"id": "s_third", "first_name": "Rosa"},
                {"id": "s_invited", "first_name": "Kai"},
                {"id": "s_outside", "first_name": "Noah"},
            ]
        )
        tables["group_members"] = [
            {
                "group_id": "g_41",
                "student_id": student_id,
                "invitation_status": invitation_status,
                "arrived_at": None,
            }
            for student_id, invitation_status in (
                ("s_current", "accepted"),
                ("s_other", "accepted"),
                ("s_third", "accepted"),
                ("s_invited", "invited"),
            )
        ]
        return tables


if __name__ == "__main__":
    unittest.main()
