"""Seed data, for `python seed.py` and for POST /admin/reset.

One module so the CLI and the demo-reset endpoint cannot drift. AGENTS.md:
the seed wipes and recreates rows where `is_seed` is true, so real signups
survive a reset.

What a seed needs to produce, in order, because each step depends on the one
before it:

  1. Reference data, the languages and tags onboarding offers.
  2. Buildings, because a group with no building has nowhere to meet and the
     map has nothing to draw.
  3. Fake students on the same preset ids a real student can pick, so the
     preset they choose already has people on it.
  4. Groups, by running the matcher over them.

=========================== COORDINATES ===========================
The latitudes and longitudes below are approximate. They put each pin on
the right part of campus and no closer, which is the same warning
frontend/src/lib/mapConfig.js carries. Check each one against
OpenStreetMap before the demo.
===================================================================
"""

import logging
import random
from dataclasses import dataclass
from datetime import date

from .matching import next_matching_dates, run_matching
from .presets import PRESETS
from .repositories.base import execute
from .repositories.reference_data import ReferenceDataRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedResult:
    buildings: int
    students: int
    groups: int


BUILDINGS: tuple[dict[str, object], ...] = (
    {"slug": "nest", "name": "The Nest", "lat": 49.2665, "lng": -123.2497, "is_indoor": True},
    {"slug": "ikb", "name": "Irving K Barber Learning Centre", "lat": 49.2677, "lng": -123.2525, "is_indoor": True},
    {"slug": "koerner", "name": "Koerner Library", "lat": 49.2659, "lng": -123.2555, "is_indoor": True},
    {"slug": "life", "name": "Life Building", "lat": 49.2685, "lng": -123.2490, "is_indoor": True},
    {"slug": "buchanan", "name": "Buchanan Courtyard", "lat": 49.2690, "lng": -123.2550, "is_indoor": False},
    {"slug": "angus", "name": "Henry Angus", "lat": 49.2648, "lng": -123.2535, "is_indoor": True},
    {"slug": "icics", "name": "ICICS", "lat": 49.2615, "lng": -123.2490, "is_indoor": True},
    {"slug": "woodward", "name": "Woodward Library", "lat": 49.2640, "lng": -123.2465, "is_indoor": True},
)

NAMES = (
    "Ji-woo", "Amir", "Rosa", "Wei", "Noor", "Dev", "Mina", "Tomas",
    "Aisha", "Kenji", "Lucia", "Omar", "Priya", "Yuki", "Hana", "Luc",
    "Sana", "Diego", "Mei", "Arjun", "Zara", "Theo", "Nadia", "Ravi",
)

# Slugs from reference_data.DEFAULT_STUDENT_TAGS. A slug that is not in that
# table cannot be resolved and the whole seed would fail on it.
TAGS = ("international", "transfer", "exchange", "commuter", "resident", "first-term")
LANGUAGES = ("en", "zh", "yue", "ko", "ja", "pa", "hi", "fr", "es")

SEED_STUDENT_COUNT = 60


def reseed(client, *, student_count: int = SEED_STUDENT_COUNT) -> SeedResult:
    """Recreate every seed row and re-run matching over it.

    Only rows marked is_seed are removed, so a student who signed up on a
    real phone keeps their profile across a reset. Their group memberships do
    go, because the groups themselves are seed-era rows.
    """
    reference = ReferenceDataRepository(client)
    reference.seed_defaults()

    buildings = _seed_buildings(client)
    _delete_seed_students(client)
    student_ids, days = _seed_students(client, student_count)
    groups = _rematch(client, days)

    return SeedResult(buildings=buildings, students=len(student_ids), groups=groups)


def _seed_buildings(client) -> int:
    # buildings.code_secret is NOT NULL in sql/schema.sql and nothing reads
    # it: it belonged to the building-QR idea, which the product dropped in
    # favour of member-to-member check-in codes. Supplying an inert value is
    # what lets a seed insert succeed without reviving the column's meaning.
    # These strings are never read, returned, or accepted as check-in codes.
    rows = execute(
        client.table("buildings").upsert(
            [
                {**building, "code_secret": f"obsolete-{building['slug']}"}
                for building in BUILDINGS
            ],
            on_conflict="slug",
        ),
        "seed buildings",
    )
    return len(rows)


def _delete_seed_students(client) -> None:
    """Drop the fake students and anything hanging off them.

    group_members and free_blocks cascade from students in the schema, so
    deleting the students is enough for those. Groups do not cascade, because
    nothing owns them, so the empty ones are cleared separately.
    """
    execute(
        client.table("students").delete().eq("is_seed", True),
        "delete seed students",
    )
    for group in execute(
        client.table("groups").select("id").gte("on_date", date.today().isoformat()),
        "read groups for reset",
    ):
        members = execute(
            client.table("group_members")
            .select("group_id,student_id")
            .eq("group_id", str(group["id"])),
            "read group members for reset",
        )
        if not members:
            execute(
                client.table("groups").delete().eq("id", str(group["id"])),
                "delete emptied group",
            )


def _seed_students(client, count: int) -> tuple[list[str], set[int]]:
    """Fake students spread evenly over the presets, so no preset is a dead
    end. Seeded random, so the demo tells the same story twice."""
    rng = random.Random(2026)
    preset_ids = list(PRESETS)
    reference = ReferenceDataRepository(client)
    tag_ids = reference.resolve_tags(list(TAGS))

    student_ids: list[str] = []
    days: set[int] = set()

    for index in range(count):
        preset_id = preset_ids[index % len(preset_ids)]
        blocks = PRESETS[preset_id]
        created = execute(
            client.table("students").insert(
                {
                    "first_name": NAMES[index % len(NAMES)],
                    "is_seed": True,
                    "is_guest": False,
                }
            ),
            "create seed student",
        )
        student_id = str(created[0]["id"])
        student_ids.append(student_id)

        execute(
            client.table("free_blocks").insert(
                [
                    {
                        "student_id": student_id,
                        "day": day,
                        "start_time": start.strftime("%H:%M"),
                        "end_time": end.strftime("%H:%M"),
                    }
                    for day, start, end in blocks
                ]
            ),
            "create seed free blocks",
        )
        days.update(day for day, _start, _end in blocks)

        chosen = rng.sample(list(TAGS), k=rng.choice([1, 1, 2]))
        execute(
            client.table("student_tags").insert(
                [
                    {"student_id": student_id, "tag_id": tag_ids[slug]}
                    for slug in chosen
                    if slug in tag_ids
                ]
            ),
            "create seed student tags",
        )
        execute(
            client.table("student_languages").insert(
                [
                    {"student_id": student_id, "language_code": code}
                    for code in rng.sample(list(LANGUAGES), k=rng.choice([1, 2]))
                ]
            ),
            "create seed student languages",
        )

    return student_ids, days


def _rematch(client, days: set[int]) -> int:
    formed = 0
    for target_date in next_matching_dates(days, from_date=date.today()):
        result = run_matching(client, target_date, persist=True)
        formed += len(result.created_group_ids)
    return formed
