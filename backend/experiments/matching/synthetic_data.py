"""Deterministic synthetic student data for offline matching experiments."""

from __future__ import annotations

from dataclasses import dataclass, replace
from random import Random
from typing import Iterable

MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True, order=True, slots=True)
class AvailabilityInterval:
    """One weekly wall-clock availability interval."""

    day: int
    start_minute: int
    end_minute: int

    def __post_init__(self) -> None:
        if not 0 <= self.day <= 6:
            raise ValueError("day must be between 0 and 6")
        if not 0 <= self.start_minute < self.end_minute <= MINUTES_PER_DAY:
            raise ValueError("availability must be a non-empty interval within one day")


@dataclass(frozen=True, slots=True)
class SyntheticStudent:
    """Synthetic matching inputs; no field contains real student data."""

    student_id: str
    availability: tuple[AvailabilityInterval, ...]
    tags: frozenset[str] = frozenset()
    courses: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    interests: frozenset[str] = frozenset()
    newcomer: bool = False
    hangout_count: int = 0


@dataclass(frozen=True, slots=True)
class SyntheticDataset:
    students: tuple[SyntheticStudent, ...]
    seed: int
    overlap_profile: str
    attribute_profile: str

    def free_block_rows(self) -> list[dict[str, object]]:
        """Return the row shape consumed by the production ``form_groups``."""
        return [
            {
                "student_id": student.student_id,
                "day": interval.day,
                "start_time": _format_minute(interval.start_minute),
                "end_time": _format_minute(interval.end_minute),
            }
            for student in self.students
            for interval in student.availability
        ]


TAGS = (
    "commuter",
    "resident",
    "transfer",
    "international",
    "exchange",
    "first-term",
    "graduate",
)
LANGUAGES = ("English", "Mandarin", "Cantonese", "Korean", "Hindi", "French", "Spanish")
COURSE_CLUSTERS = (
    ("CPSC 110", "CPSC 121", "MATH 100", "DSCI 100"),
    ("STAT 200", "STAT 302", "STAT 406", "MATH 302"),
    ("COMM 101", "COMM 290", "ECON 101", "ECON 102"),
    ("BIOL 112", "CHEM 121", "CHEM 123", "MICB 201"),
    ("PSYC 101", "SOCI 101", "PHIL 220", "POLI 101"),
)
INTEREST_CLUSTERS = (
    ("board games", "gaming", "anime", "sci-fi"),
    ("hiking", "climbing", "running", "skiing"),
    ("coffee", "cooking", "baking", "restaurants"),
    ("music", "concerts", "film", "photography"),
    ("startups", "coding", "data science", "robotics"),
)

# Real student timetables create peaks around lunch and mid-afternoon rather
# than uniform availability. Values are minute offsets in local wall time.
AVAILABILITY_TEMPLATES = (
    (9 * 60, 10 * 60 + 30),
    (10 * 60, 12 * 60),
    (11 * 60 + 30, 13 * 60),
    (12 * 60, 14 * 60),
    (13 * 60, 15 * 60),
    (14 * 60 + 30, 16 * 60 + 30),
    (16 * 60, 18 * 60),
)

ATTRIBUTE_VARIANTS = (
    "strong_clustered",
    "weakly_correlated",
    "permuted",
    "sparse",
)


def generate_dataset(
    population_size: int,
    *,
    seed: int,
    overlap_profile: str = "medium",
    attribute_profile: str = "clustered",
) -> SyntheticDataset:
    """Generate realistic-looking but entirely synthetic weekly inputs.

    The seed controls every random decision. Overlap profiles change how much
    schedules concentrate around shared templates, while attribute profiles
    control whether latent communities are strong or diffuse.
    """
    if population_size < 0:
        raise ValueError("population_size must be non-negative")
    if overlap_profile not in {"low", "medium", "high"}:
        raise ValueError("overlap_profile must be low, medium, or high")
    if attribute_profile not in {"clustered", "dispersed"}:
        raise ValueError("attribute_profile must be clustered or dispersed")

    rng = Random(seed)
    students = tuple(
        _generate_student(index, rng, overlap_profile, attribute_profile)
        for index in range(population_size)
    )
    return SyntheticDataset(students, seed, overlap_profile, attribute_profile)


def derive_attribute_variant(
    dataset: SyntheticDataset,
    profile: str,
    *,
    seed: int,
) -> SyntheticDataset:
    """Change attribute signal while preserving schedules and non-attributes.

    ``weakly_correlated`` independently shuffles half of each feature's profile
    bundles. ``permuted`` independently shuffles every feature bundle. Both
    preserve exact feature-value frequencies. ``sparse`` models missing input
    by dropping most values and intentionally does not preserve frequencies.
    """
    if profile not in ATTRIBUTE_VARIANTS:
        raise ValueError(
            "attribute variant must be one of " + ", ".join(ATTRIBUTE_VARIANTS)
        )
    if profile == "strong_clustered":
        return replace(dataset, attribute_profile=profile)

    rng = Random(seed)
    students = list(dataset.students)
    features = ("tags", "courses", "languages", "interests")
    replacements: dict[str, list[frozenset[str]]] = {}
    if profile in {"weakly_correlated", "permuted"}:
        fraction = 0.5 if profile == "weakly_correlated" else 1.0
        for feature in features:
            values = [getattr(student, feature) for student in students]
            replacements[feature] = _permute_bundles(values, rng, fraction)
    else:
        for feature in features:
            replacements[feature] = [
                _sparsify(getattr(student, feature), rng) for student in students
            ]

    transformed = tuple(
        replace(
            student,
            **{
                feature: replacements[feature][index]
                for feature in features
            },
        )
        for index, student in enumerate(students)
    )
    return SyntheticDataset(
        transformed,
        dataset.seed,
        dataset.overlap_profile,
        profile,
    )


def _generate_student(
    index: int,
    rng: Random,
    overlap_profile: str,
    attribute_profile: str,
) -> SyntheticStudent:
    community = rng.randrange(len(COURSE_CLUSTERS))
    newcomer = rng.random() < 0.32
    hangout_count = 0 if newcomer else _weighted_choice(rng, (0, 1, 2, 3, 5), (15, 28, 27, 20, 10))

    days_count = _weighted_choice(rng, (2, 3, 4, 5), (8, 27, 42, 23))
    days = sorted(rng.sample(range(5), days_count))
    intervals = tuple(
        sorted(
            interval
            for day in days
            for interval in _availability_for_day(day, rng, overlap_profile)
        )
    )

    tags = _sample_tags(rng, newcomer)
    courses = _sample_cluster_values(rng, COURSE_CLUSTERS, community, attribute_profile, 2, 4)
    interests = _sample_cluster_values(rng, INTEREST_CLUSTERS, community, attribute_profile, 1, 3)
    languages = {"English"}
    if rng.random() < 0.42:
        languages.add(rng.choice(LANGUAGES[1:]))
    if rng.random() < 0.05:
        languages.add(rng.choice(LANGUAGES[1:]))

    return SyntheticStudent(
        student_id=f"synthetic-{index:05d}",
        availability=intervals,
        tags=frozenset(tags),
        courses=frozenset(courses),
        languages=frozenset(languages),
        interests=frozenset(interests),
        newcomer=newcomer,
        hangout_count=hangout_count,
    )


def _availability_for_day(
    day: int,
    rng: Random,
    overlap_profile: str,
) -> tuple[AvailabilityInterval, ...]:
    if overlap_profile == "high":
        template_weights = (4, 8, 16, 24, 24, 16, 8)
        jitter_choices = (-15, 0, 0, 0, 15)
    elif overlap_profile == "medium":
        template_weights = (8, 12, 16, 18, 18, 16, 12)
        jitter_choices = (-30, -15, 0, 0, 15, 30)
    else:
        template_weights = (14, 14, 14, 14, 14, 14, 14)
        jitter_choices = (-45, -30, -15, 0, 15, 30, 45)

    template = _weighted_choice(rng, AVAILABILITY_TEMPLATES, template_weights)
    jitter = rng.choice(jitter_choices)
    start = max(8 * 60, template[0] + jitter)
    end = min(19 * 60, template[1] + jitter)
    primary = AvailabilityInterval(day, start, end)

    # A minority of schedules contain a second disjoint gap. This matters for
    # testing duplicate prevention when one person covers multiple candidates.
    if rng.random() >= 0.18:
        return (primary,)
    candidates = [
        item
        for item in AVAILABILITY_TEMPLATES
        if item[1] <= start - 30 or item[0] >= end + 30
    ]
    if not candidates:
        return (primary,)
    second_start, second_end = rng.choice(candidates)
    second = AvailabilityInterval(day, second_start, second_end)
    return tuple(sorted((primary, second)))


def _sample_tags(rng: Random, newcomer: bool) -> set[str]:
    tags: set[str] = set()
    tags.add("resident" if rng.random() < 0.38 else "commuter")
    if newcomer:
        tags.add("first-term")
    for tag, probability in (
        ("transfer", 0.14),
        ("international", 0.22),
        ("exchange", 0.06),
        ("graduate", 0.17),
    ):
        if rng.random() < probability:
            tags.add(tag)
    return tags


def _sample_cluster_values(
    rng: Random,
    clusters: tuple[tuple[str, ...], ...],
    community: int,
    profile: str,
    minimum: int,
    maximum: int,
) -> set[str]:
    count = rng.randint(minimum, maximum)
    home = clusters[community % len(clusters)]
    all_values = tuple(value for cluster in clusters for value in cluster)
    selected: set[str] = set()
    home_probability = 0.82 if profile == "clustered" else 0.38
    while len(selected) < count:
        pool = home if rng.random() < home_probability else all_values
        selected.add(rng.choice(pool))
    return selected


def _weighted_choice(rng: Random, values: Iterable, weights: Iterable[int]):
    values_tuple = tuple(values)
    weights_tuple = tuple(weights)
    return rng.choices(values_tuple, weights=weights_tuple, k=1)[0]


def _permute_bundles(
    values: list[frozenset[str]], rng: Random, fraction: float
) -> list[frozenset[str]]:
    result = list(values)
    count = int(len(values) * fraction)
    if count < 2:
        return result
    indices = sorted(rng.sample(range(len(values)), count))
    shuffled = [values[index] for index in indices]
    rng.shuffle(shuffled)
    for index, value in zip(indices, shuffled):
        result[index] = value
    return result


def _sparsify(values: frozenset[str], rng: Random) -> frozenset[str]:
    if rng.random() < 0.60:
        return frozenset()
    return frozenset(value for value in values if rng.random() < 0.35)


def _format_minute(minute: int) -> str:
    hour, remainder = divmod(minute, 60)
    return f"{hour:02d}:{remainder:02d}:00"
