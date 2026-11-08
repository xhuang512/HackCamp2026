"""Controlled Phase 2 ablation for similarity-aware matching."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .evaluate import EvaluationRow, evaluate_dataset, summarize
from .similarity import SimilarityWeights
from .strategies import (
    FeasibleGreedyStrategy,
    ProductionGreedyStrategy,
    SimilarityGreedyStrategy,
    SimilarityLocalSearchStrategy,
)
from .synthetic_data import (
    ATTRIBUTE_VARIANTS,
    derive_attribute_variant,
    generate_dataset,
)


@dataclass(frozen=True, slots=True)
class PairedDifference:
    comparison: str
    population_size: int
    seed: int
    overlap_profile: str
    attribute_profile: str
    coverage_absolute: float
    similarity_absolute: float
    similarity_relative: float | None
    newcomer_coverage_absolute: float
    runtime_seconds_absolute: float
    runtime_relative: float | None
    feasible_group_count_difference: int
    groups_of_3_difference: int
    groups_of_4_difference: int
    groups_of_5_difference: int
    hard_constraint_violation_difference: int


def run_ablation(
    sizes: Sequence[int],
    seeds: Sequence[int],
    attribute_profiles: Sequence[str],
    *,
    overlap_profile: str,
    local_search_budget: int,
) -> tuple[list[EvaluationRow], list[PairedDifference]]:
    """Run all strategies with schedules held fixed across attribute variants."""
    weights = SimilarityWeights().normalized()
    strategies = (
        ProductionGreedyStrategy(),
        FeasibleGreedyStrategy(weights),
        SimilarityGreedyStrategy(weights),
        SimilarityLocalSearchStrategy(
            weights, operation_budget=local_search_budget
        ),
    )
    rows: list[EvaluationRow] = []
    paired: list[PairedDifference] = []

    for size in sizes:
        for seed in seeds:
            base = generate_dataset(
                size,
                seed=seed,
                overlap_profile=overlap_profile,
                attribute_profile="clustered",
            )
            for profile in attribute_profiles:
                dataset = derive_attribute_variant(
                    base,
                    profile,
                    seed=seed * 1009 + size,
                )
                dataset_rows = evaluate_dataset(
                    dataset,
                    strategies,
                    weights=weights,
                )
                rows.extend(dataset_rows)
                paired.extend(_paired_differences(dataset_rows))
    return rows, paired


def _paired_differences(
    rows: Sequence[EvaluationRow],
) -> list[PairedDifference]:
    by_strategy = {row.strategy: row for row in rows}
    comparisons = (
        ("similarity_greedy-minus-feasible_greedy", "similarity_greedy", "feasible_greedy"),
        (
            "similarity_local_search-minus-feasible_greedy",
            "similarity_local_search",
            "feasible_greedy",
        ),
        (
            "similarity_local_search-minus-similarity_greedy",
            "similarity_local_search",
            "similarity_greedy",
        ),
    )
    differences: list[PairedDifference] = []
    for label, treatment_name, control_name in comparisons:
        treatment = by_strategy[treatment_name]
        control = by_strategy[control_name]
        differences.append(
            PairedDifference(
                comparison=label,
                population_size=treatment.population_size,
                seed=treatment.seed,
                overlap_profile=treatment.overlap_profile,
                attribute_profile=treatment.attribute_profile,
                coverage_absolute=treatment.match_rate - control.match_rate,
                similarity_absolute=(
                    treatment.mean_group_similarity
                    - control.mean_group_similarity
                ),
                similarity_relative=_relative_change(
                    treatment.mean_group_similarity,
                    control.mean_group_similarity,
                ),
                newcomer_coverage_absolute=(
                    treatment.newcomer_coverage - control.newcomer_coverage
                ),
                runtime_seconds_absolute=(
                    treatment.runtime_seconds - control.runtime_seconds
                ),
                runtime_relative=_relative_change(
                    treatment.runtime_seconds,
                    control.runtime_seconds,
                ),
                feasible_group_count_difference=(
                    treatment.feasible_group_count
                    - control.feasible_group_count
                ),
                groups_of_3_difference=(
                    treatment.groups_of_3 - control.groups_of_3
                ),
                groups_of_4_difference=(
                    treatment.groups_of_4 - control.groups_of_4
                ),
                groups_of_5_difference=(
                    treatment.groups_of_5 - control.groups_of_5
                ),
                hard_constraint_violation_difference=(
                    treatment.hard_constraint_violations
                    - control.hard_constraint_violations
                ),
            )
        )
    return differences


def summarize_paired(
    differences: Sequence[PairedDifference],
) -> list[dict[str, object]]:
    """Summarize paired deltas across seeds for every size/profile pair."""
    grouped: dict[tuple[object, ...], list[PairedDifference]] = {}
    for difference in differences:
        key = (
            difference.comparison,
            difference.population_size,
            difference.attribute_profile,
        )
        grouped.setdefault(key, []).append(difference)

    output: list[dict[str, object]] = []
    for (comparison, size, profile), samples in sorted(grouped.items()):
        output.append(
            {
                "comparison": comparison,
                "population_size": size,
                "attribute_profile": profile,
                "paired_seeds": len(samples),
                "coverage_absolute_mean": _paired_mean(
                    samples, "coverage_absolute"
                ),
                "coverage_absolute_stdev": _paired_stdev(
                    samples, "coverage_absolute"
                ),
                "similarity_absolute_mean": _paired_mean(
                    samples, "similarity_absolute"
                ),
                "similarity_absolute_stdev": _paired_stdev(
                    samples, "similarity_absolute"
                ),
                "similarity_relative_mean": _paired_mean(
                    samples, "similarity_relative"
                ),
                "similarity_worse_cases": sum(
                    sample.similarity_absolute < -1e-12 for sample in samples
                ),
                "coverage_worse_cases": sum(
                    sample.coverage_absolute < -1e-12 for sample in samples
                ),
                "newcomer_coverage_absolute_mean": _paired_mean(
                    samples, "newcomer_coverage_absolute"
                ),
                "runtime_seconds_absolute_mean": _paired_mean(
                    samples, "runtime_seconds_absolute"
                ),
                "runtime_relative_mean": _paired_mean(
                    samples, "runtime_relative"
                ),
            }
        )
    return output


def write_ablation_results(
    rows: Sequence[EvaluationRow],
    paired: Sequence[PairedDifference],
    *,
    json_path: Path,
    csv_path: Path,
    paired_csv_path: Path,
) -> None:
    for path in (json_path, csv_path, paired_csv_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experiment": "controlled_similarity_ablation",
        "objective_order": ["hard_feasibility", "coverage", "similarity"],
        "controlled_baseline": "feasible_greedy",
        "attribute_variants": {
            "strong_clustered": "original latent-community attributes",
            "weakly_correlated": "independent half-profile permutations",
            "permuted": "independent full-profile permutations",
            "sparse": "60% fully missing, then 35% value retention",
        },
        "rows": [asdict(row) for row in rows],
        "strategy_summary": summarize(rows),
        "paired_differences": [asdict(item) for item in paired],
        "paired_summary": summarize_paired(paired),
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_csv(csv_path, [asdict(row) for row in rows])
    _write_csv(paired_csv_path, [asdict(item) for item in paired])


def print_summary(rows: Sequence[EvaluationRow]) -> None:
    grouped: dict[tuple[str, int], list[EvaluationRow]] = {}
    for row in rows:
        grouped.setdefault((row.strategy, row.population_size), []).append(row)
    headers = ("strategy", "n", "match%", "similarity", "newcomer%", "seconds", "violations")
    print("  ".join(headers))
    print("  ".join("-" * len(header) for header in headers))
    for (strategy, size), samples in sorted(grouped.items()):
        print(
            "  ".join(
                (
                    strategy,
                    str(size),
                    f"{100 * statistics.fmean(row.match_rate for row in samples):.2f}",
                    f"{statistics.fmean(row.mean_group_similarity for row in samples):.4f}",
                    f"{100 * statistics.fmean(row.newcomer_coverage for row in samples):.2f}",
                    f"{statistics.fmean(row.runtime_seconds for row in samples):.4f}",
                    str(sum(row.hard_constraint_violations for row in samples)),
                )
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the controlled Phase 2 similarity ablation."
    )
    parser.add_argument("--sizes", default="100,500,2000")
    parser.add_argument("--seeds", default="17,41,73")
    parser.add_argument("--overlap", default="medium", choices=("low", "medium", "high"))
    parser.add_argument("--attributes", default=",".join(ATTRIBUTE_VARIANTS))
    parser.add_argument("--local-search-budget", type=int, default=20_000)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("experiments/matching/ablation_results.json"),
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path("experiments/matching/ablation_results.csv"),
    )
    parser.add_argument(
        "--paired-csv-output",
        type=Path,
        default=Path("experiments/matching/ablation_paired.csv"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profiles = _parse_strings(args.attributes)
    unknown = set(profiles) - set(ATTRIBUTE_VARIANTS)
    if unknown:
        raise ValueError(f"unknown attribute variant(s): {', '.join(sorted(unknown))}")
    rows, paired = run_ablation(
        _parse_ints(args.sizes),
        _parse_ints(args.seeds),
        profiles,
        overlap_profile=args.overlap,
        local_search_budget=args.local_search_budget,
    )
    print_summary(rows)
    write_ablation_results(
        rows,
        paired,
        json_path=args.json_output,
        csv_path=args.csv_output,
        paired_csv_path=args.paired_csv_output,
    )
    print(f"\nJSON:       {args.json_output}")
    print(f"Rows CSV:   {args.csv_output}")
    print(f"Paired CSV: {args.paired_csv_output}")
    return 0


def _relative_change(treatment: float, control: float) -> float | None:
    if control == 0:
        return 0.0 if treatment == 0 else None
    return (treatment - control) / control


def _paired_mean(
    samples: Sequence[PairedDifference], field: str
) -> float | None:
    values = [
        float(value)
        for sample in samples
        if (value := getattr(sample, field)) is not None
    ]
    return statistics.fmean(values) if values else None


def _paired_stdev(samples: Sequence[PairedDifference], field: str) -> float:
    values = [float(getattr(sample, field)) for sample in samples]
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]) if rows else [],
            lineterminator="\n",
        )
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def _parse_strings(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_ints(value: str) -> list[int]:
    return [int(item) for item in _parse_strings(value)]


if __name__ == "__main__":
    raise SystemExit(main())
