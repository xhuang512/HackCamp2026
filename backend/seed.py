"""Seed the demo: reference data, buildings, fake students and their groups.

Idempotent. Rows marked is_seed are replaced on each run; real signups are
left alone. The same code runs behind POST /admin/reset, in app/demo.py, so
the stage reset and this CLI cannot drift.
"""

import argparse

from app.db import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    create_supabase_client,
)
from app.demo import SEED_STUDENT_COUNT, reseed
from app.repositories import RepositoryError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--students",
        type=int,
        default=SEED_STUDENT_COUNT,
        help=f"How many fake students to create (default {SEED_STUDENT_COUNT})",
    )
    args = parser.parse_args()
    try:
        result = reseed(create_supabase_client(), student_count=args.students)
    except (
        DatabaseConfigurationError,
        DatabaseConnectionError,
        RepositoryError,
    ) as exc:
        parser.error(str(exc))
    print(
        f"seeded {result.buildings} buildings, {result.students} students "
        f"and {result.groups} groups"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
