import unittest

from experiments.matching.evaluate import evaluate_dataset
from experiments.matching.similarity import (
    SimilarityWeights,
    group_similarity,
    jaccard,
    pair_similarity,
)
from experiments.matching.strategies import (
    MatchGroup,
    ProductionGreedyStrategy,
    SimilarityGreedyStrategy,
    SimilarityLocalSearchStrategy,
    feasible_student_windows,
    validate_groups,
)
from experiments.matching.synthetic_data import (
    AvailabilityInterval,
    SyntheticDataset,
    SyntheticStudent,
    generate_dataset,
)


class SyntheticDataTests(unittest.TestCase):
    def test_fixed_seed_is_reproducible(self) -> None:
        first = generate_dataset(100, seed=41)
        second = generate_dataset(100, seed=41)

        self.assertEqual(first, second)

    def test_different_seed_changes_data(self) -> None:
        self.assertNotEqual(
            generate_dataset(20, seed=1).students,
            generate_dataset(20, seed=2).students,
        )

    def test_generator_has_weekly_availability_and_nonuniform_attributes(self) -> None:
        dataset = generate_dataset(500, seed=17)

        self.assertTrue(all(student.availability for student in dataset.students))
        self.assertGreater(
            len({student.availability for student in dataset.students}), 20
        )
        self.assertTrue(any(student.newcomer for student in dataset.students))
        self.assertTrue(any(not student.newcomer for student in dataset.students))


class SimilarityTests(unittest.TestCase):
    def test_jaccard(self) -> None:
        self.assertEqual(jaccard({"a", "b"}, {"b", "c"}), 1 / 3)
        self.assertEqual(jaccard({"a"}, {"a"}), 1.0)
        self.assertEqual(jaccard({"a"}, set()), 0.0)

    def test_empty_or_missing_attributes_are_not_perfect_matches(self) -> None:
        self.assertEqual(jaccard(set(), set()), 0.0)
        self.assertEqual(jaccard(None, None), 0.0)
        self.assertEqual(pair_similarity(_student("a"), _student("b")), 0.0)

    def test_weights_are_normalized_and_validated(self) -> None:
        weights = SimilarityWeights(tags=2, courses=1, languages=1, interests=0).normalized()

        self.assertAlmostEqual(weights.tags, 0.5)
        self.assertAlmostEqual(sum(getattr(weights, name) for name in ("tags", "courses", "languages", "interests")), 1.0)
        with self.assertRaises(ValueError):
            SimilarityWeights(tags=-1).normalized()
        with self.assertRaises(ValueError):
            SimilarityWeights(0, 0, 0, 0).normalized()

    def test_group_similarity_is_mean_pairwise_score(self) -> None:
        students = [
            _student("a", tags={"x"}),
            _student("b", tags={"x"}),
            _student("c", tags={"y"}),
        ]
        tag_only = SimilarityWeights(1, 0, 0, 0)

        self.assertAlmostEqual(group_similarity(students, tag_only), 1 / 3)


class FeasibilityTests(unittest.TestCase):
    def test_exactly_thirty_minutes_is_feasible(self) -> None:
        students = [_student(name, start=600, end=630) for name in ("a", "b", "c")]
        group = MatchGroup(1, 600, 630, ("a", "b", "c"))

        self.assertTrue(validate_groups([group], students).valid)

    def test_twenty_nine_minutes_is_not_feasible(self) -> None:
        students = [_student(name, start=600, end=629) for name in ("a", "b", "c")]
        report = validate_groups(
            [MatchGroup(1, 600, 629, ("a", "b", "c"))], students
        )

        self.assertFalse(report.valid)
        self.assertIn("shorter than 30", report.violations[0])

    def test_group_size_and_student_uniqueness_are_enforced_per_day(self) -> None:
        students = [_student(name) for name in ("a", "b", "c", "d", "e", "f")]
        groups = [
            MatchGroup(1, 600, 660, ("a", "b")),
            MatchGroup(1, 600, 660, ("a", "c", "d")),
            MatchGroup(2, 600, 660, ("a", "e", "f")),
        ]
        report = validate_groups(groups, students)

        self.assertTrue(any("outside 3-5" in item for item in report.violations))
        self.assertTrue(any("appears twice on day 1" in item for item in report.violations))
        self.assertFalse(any("appears twice on day 2" in item for item in report.violations))

    def test_feasible_population_requires_three_students_in_a_common_slot(self) -> None:
        students = (_student("a"), _student("b"))

        self.assertEqual(feasible_student_windows(students), set())


class StrategyTests(unittest.TestCase):
    def test_production_baseline_is_used_unchanged_and_flags_short_overlap(self) -> None:
        dataset = SyntheticDataset(
            students=(
                _student("a", start=600, end=645),
                _student("b", start=615, end=660),
                _student("c", start=630, end=675),
            ),
            seed=1,
            overlap_profile="medium",
            attribute_profile="clustered",
        )

        outcome = ProductionGreedyStrategy().match(dataset)

        self.assertEqual(len(outcome.groups), 1)
        self.assertEqual(outcome.groups[0].end_minute - outcome.groups[0].start_minute, 15)
        self.assertFalse(outcome.validation.valid)

    def test_similarity_greedy_is_feasible_and_deterministic(self) -> None:
        dataset = generate_dataset(100, seed=73)
        strategy = SimilarityGreedyStrategy()

        first = strategy.match(dataset)
        second = strategy.match(dataset)

        self.assertEqual(first.groups, second.groups)
        self.assertTrue(first.validation.valid, first.validation.violations)

    def test_local_search_preserves_coverage_and_feasibility(self) -> None:
        dataset = generate_dataset(100, seed=17)
        greedy = SimilarityGreedyStrategy().match(dataset)
        searched = SimilarityLocalSearchStrategy(operation_budget=2_000).match(dataset)

        self.assertTrue(searched.validation.valid, searched.validation.violations)
        self.assertEqual(_assignments(greedy.groups), _assignments(searched.groups))
        self.assertGreaterEqual(
            _quality(searched.groups, dataset),
            _quality(greedy.groups, dataset) - 1e-12,
        )
        self.assertLessEqual(searched.search_operations, 2_000)

    def test_no_feasible_group_returns_empty_result(self) -> None:
        dataset = SyntheticDataset(
            (_student("a"), _student("b")), 5, "low", "dispersed"
        )

        for strategy in (
            ProductionGreedyStrategy(),
            SimilarityGreedyStrategy(),
            SimilarityLocalSearchStrategy(),
        ):
            with self.subTest(strategy=strategy.name):
                outcome = strategy.match(dataset)
                self.assertEqual(outcome.groups, ())
                self.assertTrue(outcome.validation.valid)

    def test_evaluation_uses_same_dataset_and_reports_required_metrics(self) -> None:
        dataset = generate_dataset(40, seed=9)

        rows = evaluate_dataset(dataset)

        self.assertEqual(len(rows), 3)
        self.assertEqual({row.population_size for row in rows}, {40})
        self.assertEqual({row.seed for row in rows}, {9})
        self.assertTrue(all(0 <= row.match_rate <= 1 for row in rows))
        self.assertTrue(all(0 <= row.newcomer_coverage <= 1 for row in rows))


def _student(
    student_id: str,
    *,
    start: int = 600,
    end: int = 660,
    day: int = 1,
    tags: set[str] | None = None,
) -> SyntheticStudent:
    return SyntheticStudent(
        student_id=student_id,
        availability=(AvailabilityInterval(day, start, end),),
        tags=frozenset(tags or ()),
    )


def _assignments(groups: tuple[MatchGroup, ...]) -> set[tuple[int, str]]:
    return {
        (group.day, student_id)
        for group in groups
        for student_id in group.student_ids
    }


def _quality(groups: tuple[MatchGroup, ...], dataset: SyntheticDataset) -> float:
    students = {student.student_id: student for student in dataset.students}
    return sum(
        group_similarity([students[item] for item in group.student_ids])
        for group in groups
    )


if __name__ == "__main__":
    unittest.main()
