"""Reusable Supabase query layer for the Hangout API."""

from app.repositories.base import (
    CheckInConflictError,
    InvitationConflictError,
    RecordNotFoundError,
    ReferenceDataError,
    RepositoryError,
)

__all__ = [
    "CheckInConflictError",
    "InvitationConflictError",
    "RecordNotFoundError",
    "ReferenceDataError",
    "RepositoryError",
]
