import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException, status
from supabase import Client, create_client

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class DatabaseConfigurationError(RuntimeError):
    """Raised when backend-only Supabase configuration is unavailable."""


class DatabaseConnectionError(RuntimeError):
    """Raised when the Supabase client cannot be created."""


@lru_cache
def create_supabase_client() -> Client:
    load_dotenv(ROOT_ENV_FILE, override=False)
    url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")

    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_KEY", service_key),
        )
        if not value
    ]
    if missing:
        raise DatabaseConfigurationError(
            f"Missing backend configuration: {', '.join(missing)}"
        )

    try:
        return create_client(url, service_key)
    except Exception as exc:
        raise DatabaseConnectionError("Could not initialize Supabase client") from exc


def get_db_client() -> Client:
    try:
        return create_supabase_client()
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
