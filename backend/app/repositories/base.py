from typing import Any


class RepositoryError(RuntimeError):
    """Raised when a database operation fails."""


class RecordNotFoundError(RepositoryError):
    """Raised when an expected database row does not exist."""


class ReferenceDataError(RepositoryError):
    """Raised when onboarding references unknown catalog data."""


class InvitationConflictError(RepositoryError):
    """Raised when an invitation response violates lifecycle rules."""


class CheckInConflictError(RepositoryError):
    """Raised when meetup attendance cannot be recorded safely."""


def database_error_code(error: BaseException) -> str | None:
    """Return Postgres/PostgREST's code from a wrapped repository error.

    RepositoryError deliberately gives routes a safe message, but a few
    migration shims need to distinguish an old check constraint from a real
    outage. The original APIError remains attached as ``__cause__``.
    """
    current: BaseException | None = error
    while current is not None:
        code = getattr(current, "code", None)
        if code is not None:
            return str(code)
        current = current.__cause__
    return None
def execute(query: Any, operation: str) -> list[dict[str, Any]]:
    try:
        response = query.execute()
    except Exception as exc:
        raise RepositoryError(f"Database operation failed: {operation}") from exc

    data = getattr(response, "data", None)
    if data is None:
        raise RepositoryError(f"Database returned no result: {operation}")
    return data
