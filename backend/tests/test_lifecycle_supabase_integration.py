import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from supabase import create_client

from app.auth import create_guest_session
from app.db import get_db_client
from app.main import app


RUN_INTEGRATION = os.getenv("RUN_LIFECYCLE_V2_INTEGRATION") == "1"
DISPOSABLE_CONFIRMATION = "YES_DELETE_TEST_DATA"
APPLICATION_TIMEZONE = ZoneInfo("America/Vancouver")


@unittest.skipUnless(
    RUN_INTEGRATION,
    "Set RUN_LIFECYCLE_V2_INTEGRATION=1 for an explicitly disposable project",
)
class LifecycleSupabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = {
            "LIFECYCLE_TEST_SUPABASE_URL": os.getenv("LIFECYCLE_TEST_SUPABASE_URL"),
            "LIFECYCLE_TEST_SERVICE_KEY": os.getenv("LIFECYCLE_TEST_SERVICE_KEY"),
            "LIFECYCLE_TEST_ANON_KEY": os.getenv("LIFECYCLE_TEST_ANON_KEY"),
            "LIFECYCLE_TEST_PROJECT_REF": os.getenv("LIFECYCLE_TEST_PROJECT_REF"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing lifecycle test configuration: {', '.join(missing)}")
        if os.getenv("LIFECYCLE_TEST_CONFIRM_DISPOSABLE") != DISPOSABLE_CONFIRMATION:
            raise RuntimeError("Disposable Supabase confirmation is missing")

        cls.url = str(required["LIFECYCLE_TEST_SUPABASE_URL"])
        cls.service_key = str(required["LIFECYCLE_TEST_SERVICE_KEY"])
        cls.anon_key = str(required["LIFECYCLE_TEST_ANON_KEY"])
        project_ref = str(required["LIFECYCLE_TEST_PROJECT_REF"])
        if project_ref not in cls.url:
            raise RuntimeError("Lifecycle test URL does not match its project reference")
        if os.getenv("SUPABASE_URL") == cls.url:
            raise RuntimeError("Lifecycle tests refuse to use the configured development project")

        cls.client = create_client(cls.url, cls.service_key)
        if cls.client.table("students").select("id").limit(1).execute().data:
            raise RuntimeError("Disposable lifecycle project must start without students")
        if cls.client.table("groups").select("id").limit(1).execute().data:
            raise RuntimeError("Disposable lifecycle project must start without groups")

        cls.prefix = f"lifecycle-{uuid4().hex[:10]}"
        building = (
            cls.client.table("buildings")
            .insert(
                {
                    "slug": cls.prefix,
                    "name": "Lifecycle Test Building",
                    "lat": 49.2606,
                    "lng": -123.2460,
                    "is_indoor": True,
                    "code_secret": uuid4().hex,
                }
            )
            .execute()
            .data[0]
        )
        cls.building_id = int(building["id"])
        cls.environment = patch.dict(
            "os.environ",
            {
                "GUEST_SESSION_SECRET": "lifecycle-integration-test-secret-32-bytes",
                "CURRENT_TERM": "2026W1",
            },
            clear=False,
        )
        cls.environment.start()
        app.dependency_overrides[get_db_client] = lambda: cls.client
        cls.api = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        app.dependency_overrides.clear()
        try:
            cls._cleanup_test_rows()
            cls.client.table("buildings").delete().eq("id", cls.building_id).execute()
        finally:
            cls.environment.stop()

    def tearDown(self) -> None:
        self._cleanup_test_rows()

    def test_registration_confirmation_and_privacy_end_to_end(self) -> None:
        sessions = [self._register(f"Member {index}") for index in range(1, 5)]
        suggestion = self._get_now(sessions[0])
        self.assertEqual(suggestion.status_code, 200)
        group_id = suggestion.json()["group"]["id"]

        group = self._group(group_id)
        members = self._members(group_id)
        self.assertEqual(group["status"], "forming")
        self.assertEqual({row["invitation_status"] for row in members}, {"invited"})
        self.assertEqual(len(members), 4)

        first = self._respond(sessions[0], group_id, "join")
        repeated = self._respond(sessions[0], group_id, "join")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(self._group(group_id)["status"], "forming")

        second = self._respond(sessions[1], group_id, "join")
        self.assertEqual(second.status_code, 200)
        before_confirmation = self._get_now(sessions[0]).json()["group"]
        self.assertEqual(before_confirmation["status"], "forming")
        self.assertEqual(before_confirmation["accepted_count"], 2)
        self.assertEqual(before_confirmation["spot"]["building"], "To be announced")

        third = self._respond(sessions[2], group_id, "join")
        self.assertEqual(third.status_code, 200)
        confirmed = self._group(group_id)
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertIsNotNone(confirmed["confirmed_at"])

        accepted_view = self._get_now(sessions[0]).json()["group"]
        self.assertEqual(accepted_view["accepted_count"], 3)
        self.assertEqual(accepted_view["spot"]["building"], "Lifecycle Test Building")
        self.assertEqual(len(accepted_view["members"]), 3)

        invited_view = self._get_now(sessions[3]).json()["group"]
        self.assertEqual(invited_view["members"], [])
        self.assertEqual(invited_view["spot"]["building"], "To be announced")
        fourth = self._respond(sessions[3], group_id, "join")
        self.assertEqual(fourth.status_code, 200)
        self.assertEqual(len(self._members(group_id)), 4)
        self.assertEqual(
            sum(row["invitation_status"] == "accepted" for row in self._members(group_id)),
            4,
        )

        invalid_skip = self._respond(sessions[0], group_id, "skip")
        self.assertEqual(invalid_skip.status_code, 409)

    def test_skip_idempotency_expiration_and_malformed_group_id(self) -> None:
        student = self._create_student("Transition Member")
        group_id = self._create_group([student], deadline_delta=timedelta(days=1))
        session = self._session(student)

        first_skip = self._respond(session, group_id, "skip")
        second_skip = self._respond(session, group_id, "skip")
        rejected_join = self._respond(session, group_id, "join")
        malformed = self._respond(session, "not-a-uuid", "join")
        self.assertEqual(first_skip.status_code, 200)
        self.assertEqual(second_skip.status_code, 200)
        self.assertEqual(rejected_join.status_code, 409)
        self.assertEqual(malformed.status_code, 404)

        expired_student = self._create_student("Expired Member")
        expired_group = self._create_group(
            [expired_student], deadline_delta=timedelta(seconds=-1)
        )
        expired = self._respond(self._session(expired_student), expired_group, "join")
        self.assertEqual(expired.status_code, 409)

    def test_concurrent_third_acceptance_confirms_once(self) -> None:
        student_ids = [self._create_student(f"Concurrent {index}") for index in range(3)]
        group_id = self._create_group(student_ids, deadline_delta=timedelta(days=1))

        def accept(student_id: str) -> dict[str, object]:
            client = create_client(self.url, self.service_key)
            return client.rpc(
                "respond_to_group_invitation",
                {
                    "p_group_id": group_id,
                    "p_student_id": student_id,
                    "p_response": "accepted",
                },
            ).execute().data[0]

        with ThreadPoolExecutor(max_workers=3) as executor:
            results = list(executor.map(accept, student_ids))

        self.assertEqual(sorted(int(row["accepted_count"]) for row in results), [1, 2, 3])
        self.assertEqual(sum(row["group_status"] == "confirmed" for row in results), 1)
        group = self._group(group_id)
        self.assertEqual(group["status"], "confirmed")
        self.assertIsNotNone(group["confirmed_at"])

    def test_anon_cannot_read_write_or_execute_invitation_rpc(self) -> None:
        anon = create_client(self.url, self.anon_key)
        try:
            visible_students = anon.table("students").select("id").execute().data
        except Exception:
            visible_students = []
        self.assertEqual(visible_students, [])
        with self.assertRaises(Exception):
            anon.table("students").insert({"first_name": "Denied"}).execute()
        with self.assertRaises(Exception):
            anon.rpc(
                "respond_to_group_invitation",
                {
                    "p_group_id": str(uuid4()),
                    "p_student_id": str(uuid4()),
                    "p_response": "accepted",
                },
            ).execute()

    def _register(self, name: str) -> dict[str, str]:
        response = self.api.post(
            "/students",
            json={
                "first_name": f"{self.prefix}-{name}",
                "preset_schedule": "tue_thu_afternoon",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _create_student(self, label: str) -> str:
        row = (
            self.client.table("students")
            .insert({"first_name": f"{self.prefix}-{label}", "is_guest": True})
            .execute()
            .data[0]
        )
        return str(row["id"])

    def _create_group(
        self,
        student_ids: list[str],
        *,
        deadline_delta: timedelta,
    ) -> str:
        start = datetime.now(APPLICATION_TIMEZONE) + timedelta(days=2)
        deadline = datetime.now(APPLICATION_TIMEZONE) + deadline_delta
        row = (
            self.client.table("groups")
            .insert(
                {
                    "on_date": start.date().isoformat(),
                    "start_time": start.time().isoformat(timespec="seconds"),
                    "end_time": (start + timedelta(hours=1)).time().isoformat(timespec="seconds"),
                    "building_id": self.building_id,
                    "mode": "social",
                    "status": "forming",
                    "invite_expires_at": deadline.isoformat(),
                }
            )
            .execute()
            .data[0]
        )
        group_id = str(row["id"])
        self.client.table("group_members").insert(
            [
                {
                    "group_id": group_id,
                    "student_id": student_id,
                    "invitation_status": "invited",
                }
                for student_id in student_ids
            ]
        ).execute()
        return group_id

    @staticmethod
    def _session(student_id: str) -> dict[str, str]:
        return {"student_id": student_id, "session_token": create_guest_session(student_id)}

    def _headers(self, session: dict[str, str]) -> dict[str, str]:
        return {"Authorization": f"Bearer {session['session_token']}"}

    def _get_now(self, session: dict[str, str]):
        return self.api.get("/me/now", headers=self._headers(session))

    def _respond(self, session: dict[str, str], group_id: str, action: str):
        return self.api.post(
            f"/groups/{group_id}/{action}", headers=self._headers(session)
        )

    def _group(self, group_id: str) -> dict[str, object]:
        return (
            self.client.table("groups")
            .select("id,status,confirmed_at,invite_expires_at")
            .eq("id", group_id)
            .single()
            .execute()
            .data
        )

    def _members(self, group_id: str) -> list[dict[str, object]]:
        return (
            self.client.table("group_members")
            .select("group_id,student_id,invitation_status")
            .eq("group_id", group_id)
            .execute()
            .data
        )

    @classmethod
    def _cleanup_test_rows(cls) -> None:
        groups = (
            cls.client.table("groups")
            .select("id")
            .eq("building_id", cls.building_id)
            .execute()
            .data
        )
        for group in groups:
            cls.client.table("groups").delete().eq("id", group["id"]).execute()
        students = (
            cls.client.table("students")
            .select("id,first_name")
            .like("first_name", f"{cls.prefix}-%")
            .execute()
            .data
        )
        for student in students:
            cls.client.table("students").delete().eq("id", student["id"]).execute()


if __name__ == "__main__":
    unittest.main()
