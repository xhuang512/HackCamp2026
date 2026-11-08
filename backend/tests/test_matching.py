import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.db import create_supabase_client, get_db_client
from app.engine import form_groups
from app.matching import run_matching
from app.main import app
from app.repositories import RecordNotFoundError
from tests.fakes import FakeSupabase, seed_tables


class GroupFormationTests(unittest.TestCase):
    def test_forms_group_only_from_common_overlap(self) -> None:
        plans = form_groups(
            [
                self._block("a", "13:00", "15:00"),
                self._block("b", "14:00", "16:00"),
                self._block("c", "14:30", "15:30"),
                self._block("d", "09:00", "10:00"),
            ]
        )

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].student_ids, ("a", "b", "c"))
        self.assertEqual(plans[0].start_time.isoformat(timespec="minutes"), "14:30")
        self.assertEqual(plans[0].end_time.isoformat(timespec="minutes"), "15:00")

    def test_six_overlapping_students_split_into_two_valid_groups(self) -> None:
        plans = form_groups(
            [self._block(f"s{index}", "13:00", "15:00") for index in range(6)]
        )

        self.assertEqual([len(plan.student_ids) for plan in plans], [3, 3])
        self.assertEqual(
            {student for plan in plans for student in plan.student_ids},
            {f"s{index}" for index in range(6)},
        )

    def test_non_overlapping_students_are_not_grouped(self) -> None:
        plans = form_groups(
            [
                self._block("a", "09:00", "10:00"),
                self._block("b", "10:00", "11:00"),
                self._block("c", "11:00", "12:00"),
            ]
        )

        self.assertEqual(plans, [])

    @staticmethod
    def _block(student_id: str, start: str, end: str) -> dict[str, object]:
        return {
            "student_id": student_id,
            "day": 1,
            "start_time": start,
            "end_time": end,
        }


class MatchingPersistenceTests(unittest.TestCase):
    target_date = date(2026, 11, 10)  # Tuesday

    def setUp(self) -> None:
        tables = seed_tables()
        tables["groups"] = []
        tables["group_members"] = []
        tables["students"] = [
            {
                "id": f"s{index}",
                "first_name": f"Student {index}",
                "paused": False,
                "deleted_at": None,
            }
            for index in range(4)
        ]
        tables["free_blocks"] = [
            {
                "id": index,
                "student_id": f"s{index}",
                "day": 1,
                "start_time": "13:00:00",
                "end_time": "15:00:00",
            }
            for index in range(4)
        ]
        self.database = FakeSupabase(tables)

    def test_persists_group_and_pending_memberships(self) -> None:
        result = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(len(result.created_group_ids), 1)
        self.assertEqual(len(self.database.tables["groups"]), 1)
        group = self.database.tables["groups"][0]
        self.assertEqual(group["on_date"], "2026-11-10")
        self.assertEqual(group["building_id"], 1)
        memberships = self.database.tables["group_members"]
        self.assertEqual(len(memberships), 4)
        self.assertEqual(
            {row["invitation_status"] for row in memberships}, {"invited"}
        )

    def test_rerun_does_not_create_duplicate_groups(self) -> None:
        first = run_matching(self.database, self.target_date, persist=True)
        second = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(len(first.created_group_ids), 1)
        self.assertEqual(second.created_group_ids, ())
        self.assertEqual(second.already_assigned_students, 4)
        self.assertEqual(len(self.database.tables["groups"]), 1)
        self.assertEqual(len(self.database.tables["group_members"]), 4)

    def test_missing_building_prevents_invalid_group(self) -> None:
        self.database.tables["buildings"] = []

        with self.assertRaisesRegex(RecordNotFoundError, "No buildings exist"):
            run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(self.database.tables["groups"], [])
        self.assertEqual(self.database.tables["group_members"], [])

    def test_paused_student_is_not_matched(self) -> None:
        self.database.tables["students"][0]["paused"] = True

        result = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(len(result.created_group_ids), 1)
        member_ids = {
            row["student_id"] for row in self.database.tables["group_members"]
        }
        self.assertEqual(member_ids, {"s1", "s2", "s3"})

    def test_existing_group_is_filled_before_another_group_is_created(self) -> None:
        self.database.tables["students"] = [
            {
                "id": f"s{index}",
                "first_name": f"Student {index}",
                "paused": False,
                "deleted_at": None,
            }
            for index in range(8)
        ]
        self.database.tables["free_blocks"] = [
            {
                "id": index,
                "student_id": f"s{index}",
                "day": 1,
                "start_time": "13:00:00",
                "end_time": "15:00:00",
            }
            for index in range(8)
        ]
        self.database.tables["groups"] = [
            {
                "id": "existing",
                "on_date": self.target_date.isoformat(),
                "start_time": "13:15:00",
                "end_time": "14:30:00",
                "building_id": 1,
                "mode": "social",
                "status": "forming",
                "invite_expires_at": "2026-11-10T13:05:00-08:00",
                "confirmed_at": None,
                "status_changed_at": "2026-11-07T00:00:00Z",
                "created_at": "2026-11-07T00:00:00Z",
            }
        ]
        self.database.tables["group_members"] = [
            {
                "group_id": "existing",
                "student_id": f"s{index}",
                "invitation_status": "invited",
                "arrived_at": None,
            }
            for index in range(4)
        ]

        first = run_matching(self.database, self.target_date, persist=True)
        second = run_matching(self.database, self.target_date, persist=True)

        sizes: dict[str, int] = {}
        for membership in self.database.tables["group_members"]:
            group_id = str(membership["group_id"])
            sizes[group_id] = sizes.get(group_id, 0) + 1
        self.assertEqual(sorted(sizes.values()), [3, 5])
        self.assertEqual(first.filled_group_ids, ("existing",))
        self.assertEqual(len(first.created_group_ids), 1)
        self.assertEqual(second.created_group_ids, ())
        self.assertEqual(second.filled_group_ids, ())
        self.assertEqual(len(self.database.tables["groups"]), 2)

    def test_persistence_uses_lifecycle_columns(self) -> None:
        result = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(len(result.created_group_ids), 1)
        group = self.database.tables["groups"][0]
        self.assertEqual(group["status"], "forming")
        self.assertIn("invite_expires_at", group)
        self.assertEqual(
            {
                membership["invitation_status"]
                for membership in self.database.tables["group_members"]
            },
            {"invited"},
        )
        self.assertTrue(
            all(
                "response" not in membership
                for membership in self.database.tables["group_members"]
            )
        )

    def test_active_group_blocks_duplicate_assignment_but_cannot_be_filled(self) -> None:
        self.database.tables["groups"] = [self._existing_group("active")]
        self.database.tables["group_members"] = [
            self._membership("s0", "accepted")
        ]

        result = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(result.filled_group_ids, ())
        self.assertEqual(len(result.created_group_ids), 1)
        created_id = result.created_group_ids[0]
        self.assertEqual(
            {
                row["student_id"]
                for row in self.database.tables["group_members"]
                if row["group_id"] == created_id
            },
            {"s1", "s2", "s3"},
        )

    def test_terminal_groups_are_never_filled(self) -> None:
        for status in ("completed", "dissolved"):
            with self.subTest(status=status):
                database = FakeSupabase(self.database.tables)
                database.tables["groups"] = [self._existing_group(status)]
                database.tables["group_members"] = [
                    self._membership("s0", "accepted")
                ]

                result = run_matching(database, self.target_date, persist=True)

                self.assertEqual(result.filled_group_ids, ())
                terminal_members = [
                    row
                    for row in database.tables["group_members"]
                    if row["group_id"] == "existing"
                ]
                self.assertEqual(len(terminal_members), 1)

    def test_expired_group_does_not_block_a_new_match(self) -> None:
        expired = datetime.now(ZoneInfo("America/Vancouver")) - timedelta(minutes=1)
        self.database.tables["groups"] = [
            self._existing_group("forming", deadline=expired)
        ]
        self.database.tables["group_members"] = [self._membership("s0", "invited")]

        result = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(result.filled_group_ids, ())
        self.assertEqual(len(result.created_group_ids), 1)
        self.assertEqual(result.already_assigned_students, 0)

    def test_declined_and_expired_rows_do_not_consume_active_capacity(self) -> None:
        self.database.tables["students"] = [
            {
                "id": f"s{index}",
                "first_name": f"Student {index}",
                "paused": False,
                "deleted_at": None,
            }
            for index in range(7)
        ]
        self.database.tables["free_blocks"] = [
            {
                "id": index,
                "student_id": f"s{index}",
                "day": 1,
                "start_time": "13:00:00",
                "end_time": "15:00:00",
            }
            for index in range(7)
        ]
        self.database.tables["groups"] = [self._existing_group("forming")]
        self.database.tables["group_members"] = [
            self._membership("s0", "invited"),
            self._membership("s1", "accepted"),
            self._membership("s2", "declined"),
            self._membership("s3", "expired"),
        ]

        result = run_matching(self.database, self.target_date, persist=True)

        self.assertEqual(result.filled_group_ids, ("existing",))
        active_ids = {
            row["student_id"]
            for row in self.database.tables["group_members"]
            if row["group_id"] == "existing"
            and row["invitation_status"] in {"invited", "accepted"}
        }
        self.assertEqual(active_ids, {"s0", "s1", "s4", "s5", "s6"})

    def test_does_not_create_group_after_its_deadline(self) -> None:
        today = date.today()
        for block in self.database.tables["free_blocks"]:
            block.update(
                {
                    "day": today.weekday(),
                    "start_time": "00:00:00",
                    "end_time": "01:00:00",
                }
            )

        result = run_matching(self.database, today, persist=True)

        self.assertEqual(result.created_group_ids, ())
        self.assertEqual(self.database.tables["groups"], [])
        self.assertEqual(self.database.tables["group_members"], [])

    def _existing_group(
        self,
        status: str,
        *,
        deadline: datetime | None = None,
    ) -> dict[str, object]:
        return {
            "id": "existing",
            "on_date": self.target_date.isoformat(),
            "start_time": "13:15:00",
            "end_time": "14:30:00",
            "building_id": 1,
            "mode": "social",
            "status": status,
            "invite_expires_at": (
                deadline
                or datetime(2026, 11, 10, 13, 5, tzinfo=ZoneInfo("America/Vancouver"))
            ).isoformat(),
            "confirmed_at": None,
            "status_changed_at": "2026-11-07T00:00:00Z",
            "created_at": "2026-11-07T00:00:00Z",
        }

    @staticmethod
    def _membership(student_id: str, status: str) -> dict[str, object]:
        return {
            "group_id": "existing",
            "student_id": student_id,
            "invitation_status": status,
            "arrived_at": None,
        }


class AutomaticMatchingTests(unittest.TestCase):
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
        tables = seed_tables()
        tables["students"] = []
        tables["free_blocks"] = []
        tables["groups"] = []
        tables["group_members"] = []
        self.database = FakeSupabase(tables)
        app.dependency_overrides[get_db_client] = lambda: self.database
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()
        create_supabase_client.cache_clear()

    def test_third_signup_forms_groups_for_late_and_waiting_students(self) -> None:
        sessions = []
        for name in ("Early One", "Early Two"):
            response = self._signup(name)
            self.assertEqual(response.status_code, 201)
            sessions.append(response.json())
            self.assertEqual(self.database.tables["groups"], [])

        late = self._signup("Late Three")
        self.assertEqual(late.status_code, 201)
        sessions.append(late.json())

        self.assertEqual(len(self.database.tables["groups"]), 2)
        self.assertEqual(len(self.database.tables["group_members"]), 6)
        self.assertEqual(
            {
                membership["invitation_status"]
                for membership in self.database.tables["group_members"]
            },
            {"invited"},
        )
        for session in sessions:
            suggestion = self.client.get(
                "/me/now",
                headers={"Authorization": f"Bearer {session['session_token']}"},
            )
            self.assertEqual(suggestion.status_code, 200)
            self.assertEqual(suggestion.json()["group"]["members"], [])
            self.assertEqual(
                suggestion.json()["group"]["spot"]["building"],
                "To be announced",
            )

    def _signup(self, name: str):
        return self.client.post(
            "/students",
            json={
                "first_name": name,
                "preset_schedule": "tue_thu_afternoon",
            },
        )
