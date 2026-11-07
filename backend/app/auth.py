import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
SESSION_ALGORITHM = "HS256"
SESSION_ISSUER = "hangout-api"
SESSION_TTL = timedelta(hours=24)

bearer_scheme = HTTPBearer(auto_error=False)


def _session_secret() -> str:
    load_dotenv(ROOT_ENV_FILE, override=False)
    secret = os.getenv("GUEST_SESSION_SECRET")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Guest session signing is not configured",
        )
    if len(secret.encode("utf-8")) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Guest session signing secret must be at least 32 bytes",
        )
    return secret


def create_guest_session(student_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": student_id,
            "type": "guest",
            "iss": SESSION_ISSUER,
            "iat": now,
            "exp": now + SESSION_TTL,
        },
        _session_secret(),
        algorithm=SESSION_ALGORITHM,
    )


def ensure_guest_sessions_configured() -> None:
    _session_secret()


def get_current_student_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A guest session token is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            _session_secret(),
            algorithms=[SESSION_ALGORITHM],
            issuer=SESSION_ISSUER,
            options={"require": ["sub", "type", "exp", "iat"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired guest session token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if payload.get("type") != "guest":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid guest session token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return str(payload["sub"])
