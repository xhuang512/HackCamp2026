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
        parser.error(_format_cli_error(exc))

    action = "created" if args.apply else "planned"
    group_count = (
        len(result.created_group_ids) + len(result.filled_group_ids)
        if args.apply
        else len(result.plans) + len(result.filled_group_ids)
    )
    print(
        f"{action} {group_count} group action(s) for "
        f"{result.target_date.isoformat()}; "
        f"{result.added_memberships} student(s) added to existing groups; "
        f"{result.already_assigned_students} student(s) already assigned"
    )
    for plan in result.plans:
        print(
            f"  {plan.start_time.strftime('%H:%M')}-"
            f"{plan.end_time.strftime('%H:%M')}: "
            f"{len(plan.student_ids)} students"
        )
    return 0


def _format_cli_error(error: Exception) -> str:
    """Include PostgREST diagnostics for this development-only command."""
    lines = [str(error)]
    cause = error.__cause__
    if cause is None:
        return lines[0]

    fields = {
        name: _error_attribute(cause, name)
        for name in ("code", "message", "details", "hint")
    }
    if any(value is not None for value in fields.values()):
        lines.append("Supabase/PostgREST error:")
        lines.extend(
            f"  {name}: {value}"
            for name, value in fields.items()
            if value is not None
        )
    return "\n".join(lines)


def _error_attribute(error: BaseException, name: str) -> str | None:
    value = getattr(error, name, None)
    if value is None and error.args and isinstance(error.args[0], dict):
        value = error.args[0].get(name)
    return str(value) if value is not None else None


if __name__ == "__main__":
    raise SystemExit(main())
