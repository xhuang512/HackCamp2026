import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

from dotenv import load_dotenv
from fastapi.testclient import TestClient
from supabase import create_client

from app.auth import create_guest_session
from app.db import ROOT_ENV_FILE, create_supabase_client, get_db_client
from app.main import app
from app.timezones import APPLICATION_TIMEZONE


load_dotenv(ROOT_ENV_FILE, override=False)
RUN_INTEGRATION = os.getenv("RUN_SUPABASE_INTEGRATION") == "1"
WRITE_CONFIRMATION = "YES_I_AM_USING_A_SAFE_TEST_DATABASE"


@unittest.skipUnless(
    RUN_INTEGRATION,
    "Set RUN_SUPABASE_INTEGRATION=1 to exercise the configured test project",
)
class LifecycleSupabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        required = {
            "SUPABASE_URL": os.getenv("SUPABASE_URL"),
            "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY"),
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"Missing lifecycle test configuration: {', '.join(missing)}")
        if os.getenv("SUPABASE_TEST_CONFIRM_WRITES") != WRITE_CONFIRMATION:
            raise RuntimeError("Safe test-database write confirmation is missing")

        cls.url = str(required["SUPABASE_URL"])
        cls.service_key = str(required["SUPABASE_SERVICE_KEY"])

        create_supabase_client.cache_clear()
        cls.client = create_supabase_client()

        cls.prefix = f"lifecycle-{uuid4().hex[:10]}"
        cls.created_group_ids: set[str] = set()
        cls.created_student_ids: set[str] = set()
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
            create_supabase_client.cache_clear()
            cls.environment.stop()

    def tearDown(self) -> None:
        self._cleanup_test_rows()

    def test_registration_confirmation_and_privacy_end_to_end(self) -> None:
        sessions = [self._register(f"Member {index}") for index in range(1, 5)]
        group_id = self._create_group(
            [str(session["student_id"]) for session in sessions],
            deadline_delta=timedelta(days=1),
        )
        suggestion = self._get_now(sessions[0])
        self.assertEqual(suggestion.status_code, 200)
        self.assertEqual(suggestion.json()["group"]["id"], group_id)

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

    def test_vancouver_deadline_constraint_covers_pst_pdt_and_current_rules(self) -> None:
        cases = (
            (datetime(2025, 1, 15, 13, tzinfo=APPLICATION_TIMEZONE), -8),
            (datetime(2025, 7, 15, 13, tzinfo=APPLICATION_TIMEZONE), -7),
            (datetime(2026, 11, 10, 13, tzinfo=APPLICATION_TIMEZONE), -7),
        )
        for meeting_start, expected_offset_hours in cases:
            with self.subTest(meeting_start=meeting_start):
                self.assertEqual(
                    meeting_start.utcoffset(),
                    timedelta(hours=expected_offset_hours),
                )
                row = (
                    self.client.table("groups")
                    .insert(
                        self._group_payload(
                            meeting_start,
                            meeting_start - timedelta(minutes=10),
                        )
                    )
                    .execute()
                    .data[0]
                )
                self.created_group_ids.add(str(row["id"]))

        meeting_start = datetime(2025, 7, 15, 13, tzinfo=APPLICATION_TIMEZONE)
        with self.assertRaises(Exception) as raised:
            (
                self.client.table("groups")
                .insert(
                    self._group_payload(
                        meeting_start,
                        meeting_start + timedelta(seconds=1),
                    )
                )
                .execute()
            )
        self.assertEqual(getattr(raised.exception, "code", None), "23514")

    def _register(self, name: str) -> dict[str, str]:
        # Automatic matching is covered by deterministic repository tests. It is
        # suppressed here so a shared staging database cannot pull unrelated
        # students into groups created by this integration test.
        with patch("app.routers.students.run_matching"):
            response = self.api.post(
                "/students",
                json={
                    "first_name": f"{self.prefix}-{name}",
                    "preset_schedule": "tue_thu_afternoon",
                },
            )
        self.assertEqual(response.status_code, 201, response.text)
        session = response.json()
        self.created_student_ids.add(str(session["student_id"]))
        return session

    def _create_student(self, label: str) -> str:
        row = (
            self.client.table("students")
            .insert({"first_name": f"{self.prefix}-{label}", "is_guest": True})
            .execute()
            .data[0]
        )
        student_id = str(row["id"])
        self.created_student_ids.add(student_id)
        return student_id

    def _create_group(
        self,
        student_ids: list[str],
        *,
        deadline_delta: timedelta,
    ) -> str:
        now = datetime.now(APPLICATION_TIMEZONE)
        start = next(
            now.replace(hour=13, minute=15, second=0, microsecond=0)
            + timedelta(days=days_ahead)
            for days_ahead in range(2, 10)
            if (now + timedelta(days=days_ahead)).weekday() in {1, 3}
        )
        deadline = now + deadline_delta
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
        self.created_group_ids.add(group_id)
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

    def _group_payload(
        self,
        meeting_start: datetime,
        invite_expires_at: datetime,
    ) -> dict[str, object]:
        return {
            "on_date": meeting_start.date().isoformat(),
            "start_time": meeting_start.time().isoformat(timespec="seconds"),
            "end_time": (meeting_start + timedelta(hours=1)).time().isoformat(
                timespec="seconds"
            ),
            "building_id": self.building_id,
            "mode": "social",
            "status": "forming",
            "invite_expires_at": invite_expires_at.isoformat(),
        }

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
        for group_id in tuple(cls.created_group_ids):
            cls.client.table("groups").delete().eq("id", group_id).execute()
            cls.created_group_ids.discard(group_id)
        for student_id in tuple(cls.created_student_ids):
            cls.client.table("students").delete().eq("id", student_id).execute()
            cls.created_student_ids.discard(student_id)


@unittest.skipUnless(
    RUN_INTEGRATION and bool(os.getenv("SUPABASE_ANON_KEY")),
    "Set SUPABASE_ANON_KEY to run optional anonymous RLS checks",
)
class AnonymousSupabasePermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("SUPABASE_TEST_CONFIRM_WRITES") != WRITE_CONFIRMATION:
            raise RuntimeError("Safe test-database write confirmation is missing")
        url = os.getenv("SUPABASE_URL")
        anon_key = os.getenv("SUPABASE_ANON_KEY")
        if not url or not anon_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY are required")
        cls.anon = create_client(url, anon_key)
        create_supabase_client.cache_clear()
        cls.service = create_supabase_client()

    @classmethod
    def tearDownClass(cls) -> None:
        create_supabase_client.cache_clear()

    def test_anon_cannot_read_write_or_execute_invitation_rpc(self) -> None:
        try:
            visible_students = self.anon.table("students").select("id").execute().data
        except Exception:
            visible_students = []
        self.assertEqual(visible_students, [])
        denied_name = f"anon-denied-{uuid4().hex[:10]}"
        try:
            inserted = (
                self.anon.table("students")
                .insert({"first_name": denied_name})
                .execute()
                .data
            )
        except Exception:
            inserted = []
        if inserted:
            for row in inserted:
                self.service.table("students").delete().eq("id", row["id"]).execute()
            self.fail("Anonymous student insertion unexpectedly succeeded")
        with self.assertRaises(Exception):
            self.anon.rpc(
                "respond_to_group_invitation",
                {
                    "p_group_id": str(uuid4()),
                    "p_student_id": str(uuid4()),
                    "p_response": "accepted",
                },
            ).execute()


if __name__ == "__main__":
    unittest.main()
