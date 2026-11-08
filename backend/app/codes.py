"""Short-lived signed member-to-member meetup check-in codes.

The wire format is compatible with the integration branch::

    hc1.<student_id>.<30-second-window>.<signature>

The current and immediately previous windows are accepted. That gives a scan
at most one rotation of clock/transport grace without allowing future codes.
Group membership and meeting eligibility are deliberately verified by the
database-backed API, not encoded into or trusted from the QR payload.
"""

from __future__ import annotations

import hmac
import os
import time
from dataclasses import dataclass
from hashlib import sha256

from dotenv import load_dotenv

from app.db import ROOT_ENV_FILE

CHECKIN_WINDOW_SECONDS = 30
PREFIX = "hc1"
_SIGNATURE_CHARS = 32


class CheckInCodeConfigurationError(RuntimeError):
    """Raised when the backend cannot securely sign check-in codes."""


@dataclass(frozen=True)
class CheckInCode:
    code: str
    expires_in: int


def issue(student_id: str, *, now: float | None = None) -> CheckInCode:
    """Return the member's current signed code and seconds until rotation."""
    if not student_id or "." in student_id or any(char.isspace() for char in student_id):
        raise ValueError("student id cannot be encoded in a check-in code")
    moment = time.time() if now is None else now
    window = int(moment // CHECKIN_WINDOW_SECONDS)
    payload = f"{PREFIX}.{student_id}.{window}"
    code = f"{payload}.{_signature(payload)}"
    remaining = CHECKIN_WINDOW_SECONDS - int(moment % CHECKIN_WINDOW_SECONDS)
    return CheckInCode(code=code, expires_in=max(1, remaining))


def read(code: str, *, now: float | None = None) -> str | None:
    """Return the signed student id, or ``None`` for every invalid code."""
    if not isinstance(code, str) or len(code) > 200:
        return None
    parts = code.strip().split(".")
    if len(parts) != 4 or parts[0] != PREFIX:
        return None
    _, student_id, raw_window, signature = parts
    if not student_id or any(char.isspace() for char in student_id):
        return None
    try:
        window = int(raw_window)
    except ValueError:
        return None

    payload = f"{PREFIX}.{student_id}.{window}"
    expected = _signature(payload)
    if len(signature) != len(expected) or not hmac.compare_digest(signature, expected):
        return None

    moment = time.time() if now is None else now
    current_window = int(moment // CHECKIN_WINDOW_SECONDS)
    if window not in {current_window, current_window - 1}:
        return None
    return student_id


def _signature(payload: str) -> str:
    return hmac.new(_signing_secret(), payload.encode("utf-8"), sha256).hexdigest()[
        :_SIGNATURE_CHARS
    ]


def _signing_secret() -> bytes:
    load_dotenv(ROOT_ENV_FILE, override=False)
    value = os.getenv("GUEST_SESSION_SECRET")
    if not value or len(value.encode("utf-8")) < 32:
        raise CheckInCodeConfigurationError(
            "Check-in signing requires GUEST_SESSION_SECRET with at least 32 bytes"
        )
    return value.encode("utf-8")
