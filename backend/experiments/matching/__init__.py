"""Reproducible, synthetic-only matching strategy experiments."""

from .similarity import SimilarityWeights
from .strategies import (
    FeasibleGreedyStrategy,
    MatchGroup,
    MatchingOutcome,
    ProductionGreedyStrategy,
    SimilarityGreedyStrategy,
    SimilarityLocalSearchStrategy,
    validate_groups,
)
from .synthetic_data import AvailabilityInterval, SyntheticDataset, SyntheticStudent

__all__ = [
    "AvailabilityInterval",
    "FeasibleGreedyStrategy",
    "MatchGroup",
    "MatchingOutcome",
    "ProductionGreedyStrategy",
    "SimilarityGreedyStrategy",
    "SimilarityLocalSearchStrategy",
    "SimilarityWeights",
    "SyntheticDataset",
    "SyntheticStudent",
    "validate_groups",
]
