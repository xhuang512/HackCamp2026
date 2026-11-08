"""Offline baseline, similarity greedy, and bounded local-search strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from itertools import combinations
from typing import Iterable, Protocol, Sequence

from app.engine import form_groups

from .similarity import SimilarityWeights, group_similarity, pair_similarity
from .synthetic_data import AvailabilityInterval, SyntheticDataset, SyntheticStudent

MIN_GROUP_SIZE = 3
MAX_GROUP_SIZE = 5
MIN_OVERLAP_MINUTES = 30
SLOT_STEP_MINUTES = 15


@dataclass(frozen=True, slots=True)
class MatchGroup:
    day: int
    start_minute: int
    end_minute: int
    student_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationReport:
    violations: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


@dataclass(frozen=True, slots=True)
class MatchingOutcome:
    strategy: str
    groups: tuple[MatchGroup, ...]
    validation: ValidationReport
    search_operations: int = 0


class MatchingStrategy(Protocol):
    name: str

    def match(self, dataset: SyntheticDataset) -> MatchingOutcome: ...


def validate_groups(
    groups: Iterable[MatchGroup],
    students: Iterable[SyntheticStudent],
    *,
    min_overlap_minutes: int = MIN_OVERLAP_MINUTES,
    min_size: int = MIN_GROUP_SIZE,
    max_size: int = MAX_GROUP_SIZE,
) -> ValidationReport:
    """Validate all hard constraints for one weekly evaluation.

    A weekday is an independent assignment window. The same student may be
    matched on different weekdays, but never twice on one weekday.
    """
    student_map = {student.student_id: student for student in students}
    assigned: set[tuple[int, str]] = set()
    violations: list[str] = []

    for group_index, group in enumerate(groups):
        prefix = f"group[{group_index}]"
        member_count = len(group.student_ids)
        if not min_size <= member_count <= max_size:
            violations.append(
                f"{prefix}: size {member_count} is outside {min_size}-{max_size}"
            )
        if len(set(group.student_ids)) != member_count:
            violations.append(f"{prefix}: contains duplicate student IDs")
        if group.end_minute - group.start_minute < min_overlap_minutes:
            violations.append(
                f"{prefix}: overlap is shorter than {min_overlap_minutes} minutes"
            )
        if not 0 <= group.day <= 6 or not 0 <= group.start_minute < group.end_minute <= 1440:
            violations.append(f"{prefix}: has an invalid day or meeting interval")

        for student_id in group.student_ids:
            student = student_map.get(student_id)
            if student is None:
                violations.append(f"{prefix}: unknown student {student_id}")
                continue
            assignment = (group.day, student_id)
            if assignment in assigned:
                violations.append(
                    f"{prefix}: student {student_id} appears twice on day {group.day}"
                )
            assigned.add(assignment)
            if not _student_covers(
                student,
                group.day,
                group.start_minute,
                group.end_minute,
            ):
                violations.append(
                    f"{prefix}: student {student_id} does not cover the meeting interval"
                )
    return ValidationReport(tuple(violations))


class ProductionGreedyStrategy:
    """Adapter around the production greedy engine, without changing it."""

    name = "production_greedy"

    def match(self, dataset: SyntheticDataset) -> MatchingOutcome:
        groups = tuple(
            MatchGroup(
                day=plan.day,
                start_minute=_time_to_minute(plan.start_time),
                end_minute=_time_to_minute(plan.end_time),
                student_ids=plan.student_ids,
            )
            for plan in form_groups(dataset.free_block_rows())
        )
        return MatchingOutcome(
            strategy=self.name,
            groups=groups,
            validation=validate_groups(groups, dataset.students),
        )


class SimilarityGreedyStrategy:
    """Coverage-first feasible greedy matching with soft similarity ranking."""

    name = "similarity_greedy"

    def __init__(self, weights: SimilarityWeights = SimilarityWeights()) -> None:
        self.weights = weights.normalized()

    def match(self, dataset: SyntheticDataset) -> MatchingOutcome:
        groups = tuple(self._match_students(dataset.students))
        return MatchingOutcome(
            strategy=self.name,
            groups=groups,
            validation=validate_groups(groups, dataset.students),
        )

    def _match_students(
        self, students: Sequence[SyntheticStudent]
    ) -> list[MatchGroup]:
        student_map = {student.student_id: student for student in students}
        groups: list[MatchGroup] = []

        for day in range(5):
            remaining = {
                student.student_id
                for student in students
                if any(
                    interval.day == day
                    and interval.end_minute - interval.start_minute
                    >= MIN_OVERLAP_MINUTES
                    for interval in student.availability
                )
            }
            slots = _build_slot_index(students, day)
            flexibility = _student_slot_counts(slots)

            while True:
                candidate = _best_slot(slots, remaining)
                if candidate is None:
                    break
                slot_start, pool = candidate
                sizes = _partition_group_sizes(len(pool))
                if not sizes:
                    break

                available_pool = set(pool)
                for size in sizes:
                    selected = self._select_group(
                        available_pool,
                        size,
                        student_map,
                        flexibility,
                    )
                    if len(selected) < size:
                        break
                    start, end = _maximal_common_interval(
                        [student_map[student_id] for student_id in selected],
                        day,
                        slot_start,
                        slot_start + MIN_OVERLAP_MINUTES,
                    )
                    groups.append(MatchGroup(day, start, end, tuple(selected)))
                    available_pool.difference_update(selected)
                    remaining.difference_update(selected)

        return groups

    def _select_group(
        self,
        pool: set[str],
        size: int,
        students: dict[str, SyntheticStudent],
        flexibility: dict[str, int],
    ) -> list[str]:
        if len(pool) < size:
            return []
        # Start with a constrained/new student so flexible students remain able
        # to fill later windows. Similarity only ranks feasible companions.
        anchor = min(
            pool,
            key=lambda student_id: (
                flexibility.get(student_id, 0),
                students[student_id].hangout_count,
                student_id,
            ),
        )
        selected = [anchor]
        candidates = pool - {anchor}
        while len(selected) < size:
            best = max(
                candidates,
                key=lambda student_id: (
                    sum(
                        pair_similarity(
                            students[student_id], students[chosen], self.weights
                        )
                        for chosen in selected
                    )
                    / len(selected),
                    -students[student_id].hangout_count,
                    -flexibility.get(student_id, 0),
                    _reverse_id_key(student_id),
                ),
            )
            selected.append(best)
            candidates.remove(best)
        return sorted(selected)


class SimilarityLocalSearchStrategy:
    """Greedy seed followed by bounded, deterministic swaps and moves."""

    name = "similarity_local_search"

    def __init__(
        self,
        weights: SimilarityWeights = SimilarityWeights(),
        *,
        operation_budget: int = 20_000,
    ) -> None:
        if operation_budget < 0:
            raise ValueError("operation_budget must be non-negative")
        self.weights = weights.normalized()
        self.operation_budget = operation_budget

    def match(self, dataset: SyntheticDataset) -> MatchingOutcome:
        seed = SimilarityGreedyStrategy(self.weights).match(dataset)
        groups = list(seed.groups)
        students = {student.student_id: student for student in dataset.students}
        operations = 0

        # Each accepted operation preserves the matched student-day set, so the
        # lexicographic objective's coverage component can never decrease.
        improved = True
        while improved and operations < self.operation_budget:
            improved = False
            for left_index, right_index in combinations(range(len(groups)), 2):
                if operations >= self.operation_budget:
                    break
                left = groups[left_index]
                right = groups[right_index]
                if left.day != right.day:
                    continue
                replacement, used = self._best_pair_operation(
                    left,
                    right,
                    students,
                    self.operation_budget - operations,
                )
                operations += used
                if replacement is None:
                    continue
                groups[left_index], groups[right_index] = replacement
                improved = True
                break

        ordered = tuple(
            sorted(groups, key=lambda group: (group.day, group.start_minute, group.student_ids))
        )
        return MatchingOutcome(
            strategy=self.name,
            groups=ordered,
            validation=validate_groups(ordered, dataset.students),
            search_operations=operations,
        )

    def _best_pair_operation(
        self,
        left: MatchGroup,
        right: MatchGroup,
        students: dict[str, SyntheticStudent],
        remaining_budget: int,
    ) -> tuple[tuple[MatchGroup, MatchGroup] | None, int]:
        original_score = _groups_quality((left, right), students, self.weights)
        best_score = original_score
        best: tuple[MatchGroup, MatchGroup] | None = None
        examined = 0

        for left_id in left.student_ids:
            for right_id in right.student_ids:
                if examined >= remaining_budget:
                    return best, examined
                examined += 1
                if not _student_covers(
                    students[left_id], right.day, right.start_minute, right.end_minute
                ) or not _student_covers(
                    students[right_id], left.day, left.start_minute, left.end_minute
                ):
                    continue
                candidate_left = _replace_member(left, left_id, right_id)
                candidate_right = _replace_member(right, right_id, left_id)
                score = _groups_quality(
                    (candidate_left, candidate_right), students, self.weights
                )
                if score > best_score + 1e-12:
                    best_score = score
                    best = (candidate_left, candidate_right)

        # A move is legal only when both group sizes stay within 3-5. It also
        # preserves the matched population while allowing 4/4 -> 3/5 changes.
        for source, target, source_is_left in (
            (left, right, True),
            (right, left, False),
        ):
            if len(source.student_ids) <= MIN_GROUP_SIZE or len(target.student_ids) >= MAX_GROUP_SIZE:
                continue
            for student_id in source.student_ids:
                if examined >= remaining_budget:
                    return best, examined
                examined += 1
                if not _student_covers(
                    students[student_id],
                    target.day,
                    target.start_minute,
                    target.end_minute,
                ):
                    continue
                candidate_source = _remove_member(source, student_id)
                candidate_target = _add_member(target, student_id)
                pair = (
                    (candidate_source, candidate_target)
                    if source_is_left
                    else (candidate_target, candidate_source)
                )
                score = _groups_quality(pair, students, self.weights)
                if score > best_score + 1e-12:
                    best_score = score
                    best = pair
        return best, examined


def feasible_student_windows(
    students: Sequence[SyntheticStudent],
) -> set[tuple[int, str]]:
    """Student/day opportunities belonging to at least one feasible 30m pool."""
    feasible: set[tuple[int, str]] = set()
    for day in range(5):
        for pool in _build_slot_index(students, day).values():
            if len(pool) >= MIN_GROUP_SIZE:
                feasible.update((day, student_id) for student_id in pool)
    return feasible


def _build_slot_index(
    students: Iterable[SyntheticStudent], day: int
) -> dict[int, set[str]]:
    slots: dict[int, set[str]] = {}
    for student in students:
        for interval in student.availability:
            if interval.day != day:
                continue
            last_start = interval.end_minute - MIN_OVERLAP_MINUTES
            start = interval.start_minute
            while start <= last_start:
                slots.setdefault(start, set()).add(student.student_id)
                start += SLOT_STEP_MINUTES
            # Preserve feasibility for intervals not aligned to the 15m grid.
            if last_start >= interval.start_minute:
                slots.setdefault(last_start, set()).add(student.student_id)
    return slots


def _best_slot(
    slots: dict[int, set[str]], remaining: set[str]
) -> tuple[int, set[str]] | None:
    candidates: list[tuple[int, int, int, set[str]]] = []
    for start, student_ids in slots.items():
        pool = student_ids & remaining
        matchable = sum(_partition_group_sizes(len(pool)))
        if matchable >= MIN_GROUP_SIZE:
            candidates.append((matchable, len(pool), -start, pool))
    if not candidates:
        return None
    matchable, pool_size, negative_start, pool = max(
        candidates, key=lambda item: (item[0], item[1], item[2])
    )
    del matchable, pool_size
    return -negative_start, pool


def _partition_group_sizes(count: int) -> tuple[int, ...]:
    """Maximize covered students, then prefer groups closest to five."""
    best: tuple[int, ...] = ()
    best_covered = 0
    for threes in range(count // 3 + 1):
        for fours in range(count // 4 + 1):
            remainder = count - 3 * threes - 4 * fours
            if remainder < 0 or remainder % 5:
                continue
            fives = remainder // 5
            candidate = tuple(sorted((3,) * threes + (4,) * fours + (5,) * fives, reverse=True))
            covered = sum(candidate)
            if covered > best_covered or (
                covered == best_covered and candidate > best
            ):
                best = candidate
                best_covered = covered
    return best


def _student_slot_counts(slots: dict[int, set[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for pool in slots.values():
        for student_id in pool:
            counts[student_id] = counts.get(student_id, 0) + 1
    return counts


def _maximal_common_interval(
    students: Sequence[SyntheticStudent],
    day: int,
    required_start: int,
    required_end: int,
) -> tuple[int, int]:
    covering: list[AvailabilityInterval] = []
    for student in students:
        interval = min(
            (
                item
                for item in student.availability
                if item.day == day
                and item.start_minute <= required_start
                and item.end_minute >= required_end
            ),
            key=lambda item: (item.start_minute, item.end_minute),
        )
        covering.append(interval)
    return (
        max(item.start_minute for item in covering),
        min(item.end_minute for item in covering),
    )


def _student_covers(
    student: SyntheticStudent, day: int, start: int, end: int
) -> bool:
    return any(
        interval.day == day
        and interval.start_minute <= start
        and interval.end_minute >= end
        for interval in student.availability
    )


def _groups_quality(
    groups: Sequence[MatchGroup],
    students: dict[str, SyntheticStudent],
    weights: SimilarityWeights,
) -> float:
    return sum(
        group_similarity([students[student_id] for student_id in group.student_ids], weights)
        for group in groups
    )


def _replace_member(group: MatchGroup, old: str, new: str) -> MatchGroup:
    return MatchGroup(
        group.day,
        group.start_minute,
        group.end_minute,
        tuple(sorted(new if item == old else item for item in group.student_ids)),
    )


def _remove_member(group: MatchGroup, student_id: str) -> MatchGroup:
    return MatchGroup(
        group.day,
        group.start_minute,
        group.end_minute,
        tuple(item for item in group.student_ids if item != student_id),
    )


def _add_member(group: MatchGroup, student_id: str) -> MatchGroup:
    return MatchGroup(
        group.day,
        group.start_minute,
        group.end_minute,
        tuple(sorted((*group.student_ids, student_id))),
    )


def _time_to_minute(value: time) -> int:
    return value.hour * 60 + value.minute


def _reverse_id_key(student_id: str) -> tuple[int, ...]:
    # max() should choose the lexicographically smallest ID on a score tie.
    return tuple(-ord(character) for character in student_id)
