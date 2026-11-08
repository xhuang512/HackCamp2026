import io
import sys
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import match
from app.repositories import RepositoryError
from app.repositories.base import execute


class FakePostgrestError(Exception):
    def __init__(self) -> None:
        super().__init__(
            {
                "code": "23514",
                "message": "new row violates check constraint",
                "details": "Failing row contains test values.",
                "hint": "Inspect the lifecycle fields.",
            }
        )
        self.code = "23514"
        self.message = "new row violates check constraint"
        self.details = "Failing row contains test values."
        self.hint = "Inspect the lifecycle fields."


class FailingQuery:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def execute(self):
        raise self.error


class MatchCliErrorTests(unittest.TestCase):
    def test_execute_preserves_postgrest_exception_as_cause(self) -> None:
        database_error = FakePostgrestError()

        with self.assertRaises(RepositoryError) as raised:
            execute(FailingQuery(database_error), "create matched group")

        self.assertIs(raised.exception.__cause__, database_error)
        self.assertEqual(
            str(raised.exception),
            "Database operation failed: create matched group",
        )

    def test_cli_reports_postgrest_diagnostics(self) -> None:
        database_error = FakePostgrestError()
        try:
            raise database_error
        except FakePostgrestError as cause:
            repository_error = RepositoryError(
                "Database operation failed: create matched group"
            )
            repository_error.__cause__ = cause

        stderr = io.StringIO()
        with (
            patch.object(
                sys,
                "argv",
                ["match.py", "--date", "2026-11-10", "--apply"],
            ),
            patch.dict("os.environ", {"DEMO_MODE": "true"}),
            patch("match.create_supabase_client", return_value=object()),
            patch("match.run_matching", side_effect=repository_error),
            redirect_stderr(stderr),
            self.assertRaises(SystemExit) as raised,
        ):
            match.main()

        self.assertEqual(raised.exception.code, 2)
        output = stderr.getvalue()
        self.assertIn("Database operation failed: create matched group", output)
        self.assertIn("code: 23514", output)
        self.assertIn("message: new row violates check constraint", output)
        self.assertIn("details: Failing row contains test values.", output)
        self.assertIn("hint: Inspect the lifecycle fields.", output)


if __name__ == "__main__":
    unittest.main()
