import unittest

from app.badges import badges_for, newly_earned_badges, top_badge


class BadgeTests(unittest.TestCase):
    def test_thresholds_at_zero_one_three_and_five_checkins(self) -> None:
        expected = {
            0: [],
            1: ["first_hello"],
            3: ["first_hello", "regular"],
            5: ["first_hello", "regular", "familiar_face"],
        }
        for count, earned_slugs in expected.items():
            with self.subTest(count=count):
                badges = badges_for("student", self._memberships(count))
                self.assertEqual(
                    [badge.slug for badge in badges if badge.earned],
                    earned_slugs,
                )

    def test_locked_badge_progress_is_capped_at_its_target(self) -> None:
        badges = badges_for("student", self._memberships(2))

        self.assertEqual(badges[0].progress.model_dump(), {"current": 1, "target": 1})
        self.assertEqual(badges[1].progress.model_dump(), {"current": 2, "target": 3})
        self.assertEqual(badges[2].progress.model_dump(), {"current": 2, "target": 5})

    def test_top_badge_is_highest_earned(self) -> None:
        badge = top_badge(badges_for("student", self._memberships(3)))

        self.assertIsNotNone(badge)
        self.assertEqual(badge.slug, "regular")

    def test_new_badges_are_only_thresholds_crossed(self) -> None:
        before = badges_for("student", self._memberships(2))
        after = badges_for("student", self._memberships(3))

        self.assertEqual(
            [badge.slug for badge in newly_earned_badges(before, after)],
            ["regular"],
        )
        self.assertEqual(newly_earned_badges(after, after), [])

    def test_unarrived_and_other_students_rows_do_not_count(self) -> None:
        rows = self._memberships(1) + [
            {"student_id": "student", "arrived_at": None},
            {"student_id": "someone_else", "arrived_at": "2026-11-01T12:00:00Z"},
        ]
        badges = badges_for("student", rows)

        self.assertEqual(badges[1].progress.current, 1)

    def test_every_badge_has_a_description(self) -> None:
        for badge in badges_for("student", []):
            with self.subTest(slug=badge.slug):
                self.assertTrue(badge.description)

    @staticmethod
    def _memberships(count: int) -> list[dict]:
        return [
            {
                "student_id": "student",
                "arrived_at": f"2026-11-{index + 1:02d}T12:00:00Z",
            }
            for index in range(count)
        ]


if __name__ == "__main__":
    unittest.main()
