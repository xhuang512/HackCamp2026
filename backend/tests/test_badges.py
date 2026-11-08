import unittest

from app.badges import badges_for, newly_earned_badges, top_badge


class BadgeTests(unittest.TestCase):
    """The Campus Cat set: Community Host, Social Regular, Study Regular,
    Super Host. Two count every hangout, two count one mode."""

    def test_total_badges_unlock_at_one_and_five_hangouts(self) -> None:
        expected = {
            0: [],
            1: ["community_host"],
            4: ["community_host"],
            5: ["community_host", "super_host"],
        }
        for count, earned_slugs in expected.items():
            with self.subTest(count=count):
                badges = badges_for("student", self._memberships(count))
                self.assertEqual(
                    [badge.slug for badge in badges if badge.earned],
                    earned_slugs,
                )

    def test_mode_badges_count_only_their_own_mode(self) -> None:
        memberships = self._memberships(6)
        modes = {
            "g0": "study", "g1": "study", "g2": "study",
            "g3": "social", "g4": "social", "g5": "study",
        }

        badges = {b.slug: b for b in badges_for("student", memberships, modes)}

        # Four study hangouts, capped at the target of three.
        self.assertTrue(badges["study_regular"].earned)
        self.assertEqual(badges["study_regular"].progress.model_dump(),
                         {"current": 3, "target": 3})
        # Two social ones is one short.
        self.assertFalse(badges["social_regular"].earned)
        self.assertEqual(badges["social_regular"].progress.model_dump(),
                         {"current": 2, "target": 3})

    def test_mode_badges_stay_locked_when_no_modes_are_supplied(self) -> None:
        """A caller without the groups in hand gets them locked rather than a
        number counting the wrong thing."""
        badges = {b.slug: b for b in badges_for("student", self._memberships(9))}

        self.assertTrue(badges["super_host"].earned)
        self.assertFalse(badges["study_regular"].earned)
        self.assertFalse(badges["social_regular"].earned)
        self.assertEqual(badges["study_regular"].progress.model_dump(),
                         {"current": 0, "target": 3})

    def test_only_this_student_and_only_arrivals_count(self) -> None:
        memberships = [
            {"group_id": "g0", "student_id": "student", "arrived_at": "2026-11-01T12:00:00Z"},
            # Someone else's arrival.
            {"group_id": "g1", "student_id": "other", "arrived_at": "2026-11-02T12:00:00Z"},
            # Joined and never showed up.
            {"group_id": "g2", "student_id": "student", "arrived_at": None},
        ]

        badges = {b.slug: b for b in badges_for("student", memberships)}

        self.assertEqual(badges["super_host"].progress.model_dump(),
                         {"current": 1, "target": 5})

    def test_locked_badge_progress_is_capped_at_its_target(self) -> None:
        badges = badges_for("student", self._memberships(2))

        self.assertEqual(badges[0].progress.model_dump(), {"current": 1, "target": 1})
        self.assertEqual(badges[3].progress.model_dump(), {"current": 2, "target": 5})

    def test_top_badge_is_highest_earned(self) -> None:
        self.assertIsNone(top_badge(badges_for("student", self._memberships(0))))

        badge = top_badge(badges_for("student", self._memberships(5)))

        self.assertIsNotNone(badge)
        self.assertEqual(badge.slug, "super_host")

    def test_new_badges_are_only_thresholds_crossed(self) -> None:
        before = badges_for("student", self._memberships(4))
        after = badges_for("student", self._memberships(5))

        self.assertEqual(
            [badge.slug for badge in newly_earned_badges(before, after)],
            ["super_host"],
        )
        self.assertEqual(newly_earned_badges(after, after), [])

    @staticmethod
    def _memberships(count: int) -> list[dict]:
        return [
            {
                "group_id": f"g{index}",
                "student_id": "student",
                "arrived_at": f"2026-11-{index + 1:02d}T12:00:00Z",
            }
            for index in range(count)
        ]


if __name__ == "__main__":
    unittest.main()
