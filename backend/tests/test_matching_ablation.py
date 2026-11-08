import unittest
from collections import Counter

from experiments.matching.ablation import (
    _paired_differences,
    run_ablation,
    summarize_paired,
)
from experiments.matching.evaluate import EvaluationRow
from experiments.matching.similarity import SimilarityWeights, group_similarity
from experiments.matching.strategies import (
    FeasibleGreedyStrategy,
    MatchGroup,
    SimilarityGreedyStrategy,
    SimilarityLocalSearchStrategy,
)
from experiments.matching.synthetic_data import (
    ATTRIBUTE_VARIANTS,
    AvailabilityInterval,
    SyntheticDataset,
    SyntheticStudent,
    derive_attribute_variant,
    generate_dataset,
)


class AttributeVariantTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = generate_dataset(
            100,
            seed=41,
            overlap_profile="medium",
            attribute_profile="clustered",
        )

    def test_all_variants_preserve_schedules_and_non_attribute_fields(self) -> None:
        expected = [
            (
                student.student_id,
                student.availability,
                student.newcomer,
                student.hangout_count,
            )
            for student in self.base.students
        ]

        for profile in ATTRIBUTE_VARIANTS:
            with self.subTest(profile=profile):
                variant = derive_attribute_variant(self.base, profile, seed=7)
                actual = [
                    (
                        student.student_id,
                        student.availability,
                        student.newcomer,
                        student.hangout_count,
                    )
                    for student in variant.students
                ]
                self.assertEqual(actual, expected)

    def test_permutations_preserve_exact_attribute_frequencies(self) -> None:
        for profile in ("weakly_correlated", "permuted"):
            variant = derive_attribute_variant(self.base, profile, seed=17)
            with self.subTest(profile=profile):
                for feature in ("tags", "courses", "languages", "interests"):
                    self.assertEqual(
                        _frequency(self.base, feature),
                        _frequency(variant, feature),
                    )

    def test_sparse_variant_reduces_available_signal(self) -> None:
        sparse = derive_attribute_variant(self.base, "sparse", seed=17)

        base_values = sum(
            len(getattr(student, feature))
            for student in self.base.students
            for feature in ("tags", "courses", "languages", "interests")
        )
        sparse_values = sum(
            len(getattr(student, feature))
            for student in sparse.students
            for feature in ("tags", "courses", "languages", "interests")
        )
        self.assertLess(sparse_values, base_values / 3)
        self.assertTrue(
            any(
                not student.tags
                and not student.courses
                and not student.languages
                and not student.interests
                for student in sparse.students
            )
        )

    def test_attribute_variants_are_deterministic(self) -> None:
        first = derive_attribute_variant(self.base, "permuted", seed=73)
        second = derive_attribute_variant(self.base, "permuted", seed=73)

        self.assertEqual(first, second)


class ControlledStrategyTests(unittest.TestCase):
    def test_feasible_baseline_is_attribute_independent(self) -> None:
        strategy = FeasibleGreedyStrategy()
        expected = strategy.match(self.base_dataset()).groups

        for profile in ATTRIBUTE_VARIANTS:
            variant = derive_attribute_variant(
                self.base_dataset(), profile, seed=29
            )
            with self.subTest(profile=profile):
                outcome = strategy.match(variant)
                self.assertEqual(outcome.groups, expected)
                self.assertTrue(outcome.validation.valid)

    def test_control_and_similarity_share_feasible_coverage_pipeline(self) -> None:
        dataset = generate_dataset(100, seed=17)
        control = FeasibleGreedyStrategy().match(dataset)
        similarity = SimilarityGreedyStrategy().match(dataset)

        self.assertTrue(control.validation.valid)
        self.assertTrue(similarity.validation.valid)
        self.assertEqual(
            sorted(len(group.student_ids) for group in control.groups),
            sorted(len(group.student_ids) for group in similarity.groups),
        )

    def test_newcomer_is_only_a_tie_breaker_not_similarity_objective(self) -> None:
        students = (
            _student("anchor", tags={"x"}, hangout_count=0),
            _student("similar-veteran", tags={"x"}, hangout_count=5),
            _student("new-a", tags={"y"}, hangout_count=0),
            _student("new-b", tags={"z"}, hangout_count=0),
            _student("new-c", tags={"q"}, hangout_count=0),
            _student("new-d", tags={"r"}, hangout_count=0),
        )
        dataset = SyntheticDataset(students, 1, "medium", "strong_clustered")
        tag_only = SimilarityWeights(1, 0, 0, 0)

        similarity_group = SimilarityGreedyStrategy(tag_only).match(dataset).groups[0]
        control_group = FeasibleGreedyStrategy(tag_only).match(dataset).groups[0]

        self.assertIn("similar-veteran", similarity_group.student_ids)
        self.assertNotIn("similar-veteran", control_group.student_ids)

    def test_local_search_preserves_exact_assignments_for_every_variant(self) -> None:
        base = generate_dataset(100, seed=73)
        for profile in ATTRIBUTE_VARIANTS:
            dataset = derive_attribute_variant(base, profile, seed=11)
            greedy = SimilarityGreedyStrategy().match(dataset)
            searched = SimilarityLocalSearchStrategy(
                operation_budget=1_000
            ).match(dataset)
            with self.subTest(profile=profile):
                self.assertEqual(
                    _assignments(greedy.groups),
                    _assignments(searched.groups),
                )
                self.assertTrue(searched.validation.valid)

    def test_local_search_objective_matches_reported_mean_ordering(self) -> None:
        dataset = generate_dataset(40, seed=9)
        students = {student.student_id: student for student in dataset.students}
        greedy = SimilarityGreedyStrategy().match(dataset)
        searched = SimilarityLocalSearchStrategy(
            operation_budget=1_000
        ).match(dataset)

        greedy_sum = sum(
            group_similarity([students[item] for item in group.student_ids])
            for group in greedy.groups
        )
        searched_sum = sum(
            group_similarity([students[item] for item in group.student_ids])
            for group in searched.groups
        )
        self.assertEqual(len(greedy.groups), len(searched.groups))
        self.assertGreaterEqual(searched_sum, greedy_sum - 1e-12)
        self.assertGreaterEqual(
            searched_sum / len(searched.groups),
            greedy_sum / len(greedy.groups) - 1e-12,
        )

    @staticmethod
    def base_dataset() -> SyntheticDataset:
        return generate_dataset(80, seed=5)


class AblationEvaluationTests(unittest.TestCase):
    def test_run_uses_all_four_strategies_on_each_variant(self) -> None:
        rows, paired = run_ablation(
            [20],
            [3],
            ["strong_clustered", "sparse"],
            overlap_profile="medium",
            local_search_budget=100,
        )

        self.assertEqual(len(rows), 8)
        self.assertEqual(len(paired), 6)
        self.assertEqual(
            {row.strategy for row in rows},
            {
                "production_greedy",
                "feasible_greedy",
                "similarity_greedy",
                "similarity_local_search",
            },
        )

    def test_paired_differences_use_feasible_control(self) -> None:
        rows = [
            _row("production_greedy", 0.5, 0.1, 1.0),
            _row("feasible_greedy", 0.8, 0.2, 2.0),
            _row("similarity_greedy", 0.8, 0.3, 3.0),
            _row("similarity_local_search", 0.8, 0.33, 4.0),
        ]

        paired = _paired_differences(rows)
        greedy_delta = paired[0]
        local_delta = paired[1]

        self.assertEqual(greedy_delta.coverage_absolute, 0.0)
        self.assertAlmostEqual(greedy_delta.similarity_absolute, 0.1)
        self.assertAlmostEqual(greedy_delta.similarity_relative, 0.5)
        self.assertAlmostEqual(local_delta.similarity_absolute, 0.13)
        self.assertEqual(len(summarize_paired(paired)), 3)


def _frequency(dataset: SyntheticDataset, feature: str) -> Counter[str]:
    return Counter(
        value
        for student in dataset.students
        for value in getattr(student, feature)
    )


def _student(
    student_id: str,
    *,
    tags: set[str],
    hangout_count: int,
) -> SyntheticStudent:
    return SyntheticStudent(
        student_id=student_id,
        availability=(AvailabilityInterval(1, 600, 660),),
        tags=frozenset(tags),
        hangout_count=hangout_count,
    )


def _assignments(groups: tuple[MatchGroup, ...]) -> set[tuple[int, str]]:
    return {
        (group.day, student_id)
        for group in groups
        for student_id in group.student_ids
    }


def _row(
    strategy: str,
    coverage: float,
    similarity: float,
    runtime: float,
) -> EvaluationRow:
    return EvaluationRow(
        strategy=strategy,
        population_size=100,
        seed=17,
        overlap_profile="medium",
        attribute_profile="strong_clustered",
        feasible_student_windows=100,
        matched_student_windows=int(coverage * 100),
        unmatched_student_windows=100 - int(coverage * 100),
        match_rate=coverage,
        mean_group_similarity=similarity,
        newcomer_coverage=coverage,
        feasible_group_count=20,
        groups_of_3=0,
        groups_of_4=0,
        groups_of_5=20,
        runtime_seconds=runtime,
        hard_constraint_violations=0,
        search_operations=0,
    )


if __name__ == "__main__":
    unittest.main()
