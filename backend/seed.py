"""Idempotently seed controlled onboarding reference data."""

import argparse

from app.db import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    create_supabase_client,
)
from app.repositories import RepositoryError
from app.repositories.reference_data import ReferenceDataRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        language_count, tag_count = ReferenceDataRepository(
            create_supabase_client()
        ).seed_defaults()
    except (
        DatabaseConfigurationError,
        DatabaseConnectionError,
        RepositoryError,
    ) as exc:
        parser.error(str(exc))
    print(f"seeded {language_count} languages and {tag_count} student tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
