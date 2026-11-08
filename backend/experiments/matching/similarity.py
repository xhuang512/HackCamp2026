"""Attribute-only similarity scoring for the offline matching experiment."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from typing import Collection, Mapping, Sequence

from .synthetic_data import SyntheticStudent

FEATURE_NAMES = ("tags", "courses", "languages", "interests")


@dataclass(frozen=True, slots=True)
class SimilarityWeights:
    tags: float = 0.25
    courses: float = 0.30
    languages: float = 0.20
    interests: float = 0.25

    def normalized(self) -> "SimilarityWeights":
        values = {name: float(getattr(self, name)) for name in FEATURE_NAMES}
        if any(not isfinite(value) or value < 0 for value in values.values()):
            raise ValueError("similarity weights must be finite and non-negative")
        total = sum(values.values())
        if total <= 0:
            raise ValueError("at least one similarity weight must be positive")
        return SimilarityWeights(**{name: value / total for name, value in values.items()})

    @classmethod
    def from_mapping(cls, values: Mapping[str, float]) -> "SimilarityWeights":
        unknown = set(values) - set(FEATURE_NAMES)
        if unknown:
            raise ValueError(f"unknown similarity weight(s): {', '.join(sorted(unknown))}")
        return cls(**{name: float(values.get(name, getattr(cls(), name))) for name in FEATURE_NAMES}).normalized()


def jaccard(left: Collection[str] | None, right: Collection[str] | None) -> float:
    """Return Jaccard similarity, treating two empty/missing sets as 0."""
    left_set = set(left or ())
    right_set = set(right or ())
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def pair_similarity(
    left: SyntheticStudent,
    right: SyntheticStudent,
    weights: SimilarityWeights = SimilarityWeights(),
) -> float:
    normalized = weights.normalized()
    return sum(
        getattr(normalized, feature)
        * jaccard(getattr(left, feature), getattr(right, feature))
        for feature in FEATURE_NAMES
    )


def group_similarity(
    members: Sequence[SyntheticStudent],
    weights: SimilarityWeights = SimilarityWeights(),
) -> float:
    """Mean pairwise similarity; singleton/empty groups have no quality score."""
    pairs = tuple(combinations(members, 2))
    if not pairs:
        return 0.0
    return sum(pair_similarity(a, b, weights) for a, b in pairs) / len(pairs)
