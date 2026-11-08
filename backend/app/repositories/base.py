from typing import Any


class RepositoryError(RuntimeError):
    """Raised when a database operation fails."""


class RecordNotFoundError(RepositoryError):
    """Raised when an expected database row does not exist."""


class ReferenceDataError(RepositoryError):
    """Raised when onboarding references unknown catalog data."""


class InvitationConflictError(RepositoryError):
    """Raised when an invitation response violates lifecycle rules."""


def execute(query: Any, operation: str) -> list[dict[str, Any]]:
    try:
        response = query.execute()
    except Exception as exc:
        raise RepositoryError(f"Database operation failed: {operation}") from exc

    data = getattr(response, "data", None)
    if data is None:
        raise RepositoryError(f"Database returned no result: {operation}")
    return data
