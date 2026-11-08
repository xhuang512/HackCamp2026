"""Command-line evaluation for the offline matching experiment."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Iterable, Sequence

from .similarity import SimilarityWeights, group_similarity
from .strategies import (
    MatchGroup,
    MatchingOutcome,
    ProductionGreedyStrategy,
    SimilarityGreedyStrategy,
    SimilarityLocalSearchStrategy,
    feasible_student_windows,
)
from .synthetic_data import SyntheticDataset, generate_dataset


@dataclass(frozen=True, slots=True)
class EvaluationRow:
    strategy: str
    population_size: int
    seed: int
    overlap_profile: str
    attribute_profile: str
    feasible_student_windows: int
    matched_student_windows: int
    unmatched_student_windows: int
    match_rate: float
    mean_group_similarity: float
    newcomer_coverage: float
    groups_of_3: int
    groups_of_4: int
    groups_of_5: int
    runtime_seconds: float
    hard_constraint_violations: int
    search_operations: int


def evaluate_dataset(
    dataset: SyntheticDataset,
    strategies: Sequence | None = None,
    *,
    weights: SimilarityWeights = SimilarityWeights(),
) -> list[EvaluationRow]:
    """Evaluate every strategy against exactly the same synthetic dataset."""
    selected = strategies or (
        ProductionGreedyStrategy(),
        SimilarityGreedyStrategy(weights),
        SimilarityLocalSearchStrategy(weights),
    )
    feasible = feasible_student_windows(dataset.students)
    student_map = {student.student_id: student for student in dataset.students}
    feasible_newcomers = {
        item for item in feasible if student_map[item[1]].newcomer
    }
    rows: list[EvaluationRow] = []

    for strategy in selected:
        started = perf_counter()
        outcome: MatchingOutcome = strategy.match(dataset)
        elapsed = perf_counter() - started
        valid_groups = _valid_groups(outcome)
        matched = {
            (group.day, student_id)
            for group in valid_groups
            for student_id in group.student_ids
            if (group.day, student_id) in feasible
        }
        matched_newcomers = matched & feasible_newcomers
        similarities = [
            group_similarity(
                [student_map[student_id] for student_id in group.student_ids],
                weights,
            )
            for group in valid_groups
        ]
        sizes = [len(group.student_ids) for group in valid_groups]
        rows.append(
            EvaluationRow(
                strategy=outcome.strategy,
                population_size=len(dataset.students),
                seed=dataset.seed,
                overlap_profile=dataset.overlap_profile,
                attribute_profile=dataset.attribute_profile,
                feasible_student_windows=len(feasible),
                matched_student_windows=len(matched),
                unmatched_student_windows=max(0, len(feasible) - len(matched)),
                match_rate=_safe_ratio(len(matched), len(feasible)),
                mean_group_similarity=(
                    statistics.fmean(similarities) if similarities else 0.0
                ),
                newcomer_coverage=_safe_ratio(
                    len(matched_newcomers), len(feasible_newcomers)
                ),
                groups_of_3=sizes.count(3),
                groups_of_4=sizes.count(4),
                groups_of_5=sizes.count(5),
                runtime_seconds=elapsed,
                hard_constraint_violations=len(outcome.validation.violations),
                search_operations=outcome.search_operations,
            )
        )
    return rows


def summarize(rows: Sequence[EvaluationRow]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[EvaluationRow]] = {}
    for row in rows:
        key = (
            row.strategy,
            row.population_size,
            row.overlap_profile,
            row.attribute_profile,
        )
        grouped.setdefault(key, []).append(row)

    summaries: list[dict[str, object]] = []
    for key, samples in sorted(grouped.items()):
        strategy, size, overlap, attributes = key
        summaries.append(
            {
                "strategy": strategy,
                "population_size": size,
                "overlap_profile": overlap,
                "attribute_profile": attributes,
                "seeds": len(samples),
                "match_rate_mean": _mean(samples, "match_rate"),
                "match_rate_stdev": _stdev(samples, "match_rate"),
                "similarity_mean": _mean(samples, "mean_group_similarity"),
                "similarity_stdev": _stdev(samples, "mean_group_similarity"),
                "newcomer_coverage_mean": _mean(samples, "newcomer_coverage"),
                "runtime_seconds_mean": _mean(samples, "runtime_seconds"),
                "violations_total": sum(
                    sample.hard_constraint_violations for sample in samples
                ),
            }
        )
    return summaries


def run_experiment(
    sizes: Sequence[int],
    seeds: Sequence[int],
    overlap_profiles: Sequence[str],
    attribute_profiles: Sequence[str],
    *,
    local_search_budget: int,
) -> list[EvaluationRow]:
    weights = SimilarityWeights().normalized()
    strategies = (
        ProductionGreedyStrategy(),
        SimilarityGreedyStrategy(weights),
        SimilarityLocalSearchStrategy(
            weights, operation_budget=local_search_budget
        ),
    )
    rows: list[EvaluationRow] = []
    for size in sizes:
        for overlap in overlap_profiles:
            for attributes in attribute_profiles:
                for seed in seeds:
                    dataset = generate_dataset(
                        size,
                        seed=seed,
                        overlap_profile=overlap,
                        attribute_profile=attributes,
                    )
                    rows.extend(evaluate_dataset(dataset, strategies, weights=weights))
    return rows


def write_results(
    rows: Sequence[EvaluationRow], json_path: Path, csv_path: Path
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": "offline_similarity_matching",
        "objective_order": ["hard_feasibility", "coverage", "similarity"],
        "rows": [asdict(row) for row in rows],
        "summary": summarize(rows),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(asdict(rows[0])) if rows else [],
            lineterminator="\n",
        )
        if rows:
            writer.writeheader()
            writer.writerows(asdict(row) for row in rows)


def print_table(rows: Sequence[EvaluationRow]) -> None:
    headers = (
        "strategy",
        "n",
        "seed",
        "overlap",
        "match%",
        "similarity",
        "newcomer%",
        "seconds",
        "violations",
    )
    formatted = [
        (
            row.strategy,
            str(row.population_size),
            str(row.seed),
            row.overlap_profile,
            f"{100 * row.match_rate:.1f}",
            f"{row.mean_group_similarity:.3f}",
            f"{100 * row.newcomer_coverage:.1f}",
            f"{row.runtime_seconds:.4f}",
            str(row.hard_constraint_violations),
        )
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in formatted))
        for index in range(len(headers))
    ] if formatted else [len(header) for header in headers]
    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in formatted:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the synthetic, offline similarity matching experiment."
    )
    parser.add_argument("--sizes", default="100,500,2000")
    parser.add_argument("--seeds", default="17,41,73")
    parser.add_argument("--overlaps", default="low,medium,high")
    parser.add_argument("--attributes", default="clustered,dispersed")
    parser.add_argument("--local-search-budget", type=int, default=20_000)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("experiments/matching/results.json"),
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path("experiments/matching/results.csv"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rows = run_experiment(
        _parse_int_list(args.sizes),
        _parse_string_list(args.seeds, cast=int),
        _parse_string_list(args.overlaps),
        _parse_string_list(args.attributes),
        local_search_budget=args.local_search_budget,
    )
    print_table(rows)
    write_results(rows, args.json_output, args.csv_output)
    print(f"\nJSON: {args.json_output}")
    print(f"CSV:  {args.csv_output}")
    return 0


def _valid_groups(outcome: MatchingOutcome) -> tuple[MatchGroup, ...]:
    # Validation messages identify a group index. Invalid baseline groups are
    # excluded from coverage and quality rather than counted as valid matches.
    invalid_indices = {
        int(message.split("[", 1)[1].split("]", 1)[0])
        for message in outcome.validation.violations
        if message.startswith("group[")
    }
    return tuple(
        group
        for index, group in enumerate(outcome.groups)
        if index not in invalid_indices
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _mean(rows: Sequence[EvaluationRow], field: str) -> float:
    return statistics.fmean(float(getattr(row, field)) for row in rows)


def _stdev(rows: Sequence[EvaluationRow], field: str) -> float:
    values = [float(getattr(row, field)) for row in rows]
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _parse_int_list(value: str) -> list[int]:
    result = _parse_string_list(value, cast=int)
    if any(item < 0 for item in result):
        raise ValueError("sizes must be non-negative")
    return result


def _parse_string_list(value: str, cast=str):
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
