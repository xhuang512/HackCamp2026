import unittest
from datetime import date

from app.engine import form_groups
from app.matching import run_matching
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
        self.assertEqual({row["response"] for row in memberships}, {"pending"})

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
