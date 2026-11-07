"""Development CLI for previewing and persisting simple group matching."""

import argparse
import os
from datetime import date

from app.db import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    create_supabase_client,
)
from app.matching import run_matching
from app.repositories import RepositoryError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        required=True,
        type=date.fromisoformat,
        help="calendar date to match (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="persist groups; without this flag the command is a dry run",
    )
    args = parser.parse_args()

    try:
        client = create_supabase_client()
        if args.apply and os.getenv("DEMO_MODE", "").lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            parser.error("--apply is available only when DEMO_MODE=true")
        result = run_matching(
            client,
            args.date,
            persist=args.apply,
        )
    except (
        DatabaseConfigurationError,
        DatabaseConnectionError,
        RepositoryError,
    ) as exc:
        parser.error(str(exc))

    action = "created" if args.apply else "planned"
    print(
        f"{action} {len(result.created_group_ids) if args.apply else len(result.plans)} "
        f"group(s) for {result.target_date.isoformat()}; "
        f"{result.already_assigned_students} student(s) already assigned"
    )
    for plan in result.plans:
        print(
            f"  {plan.start_time.strftime('%H:%M')}-"
            f"{plan.end_time.strftime('%H:%M')}: "
            f"{len(plan.student_ids)} students"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
