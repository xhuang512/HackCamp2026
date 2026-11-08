"""Short-lived signed member-to-member meetup check-in codes.

The wire format is compatible with the integration branch::

Every code comes in two forms, for two different readers.

The QR payload, which nobody types:

    hc1.<student_id>.<30-second-window>.<signature>

And a six-digit typed code, for a phone whose camera will not open:

    482716

The current and immediately previous windows are accepted. That gives a scan
at most one rotation of clock and transport grace without allowing future
codes. Group membership and meeting eligibility are deliberately verified by
the database-backed API, not encoded into or trusted from the payload: the
group id is not in the code at all, it comes from the URL the code is posted
to, which is what stops a code from one group being replayed into another.

The typed form is the weaker of the two and is deliberately not a truncation
of the signature above. It is a separate HMAC over a different payload, so
reading one off a screen tells you nothing about the other. Six digits is
about 20 bits against the QR payload's 128. What keeps it usable is
everything around it: it rotates every 30 seconds, it is only accepted from a
caller who has already joined the group, and the route tries it against that
group's members alone, at most five people over two windows. A guess is worth
roughly ten chances in a million for the 30 seconds it stays current.

What a guessing attack actually costs, because the bare bit count oversells
it. The endpoint needs a valid session AND membership of the group being
guessed at, so the attacker is already inside the group. Even odds take about
70,000 requests inside the 60 seconds a code stays acceptable, and the prize
is a false check-in for an existing groupmate, which inflates the hangout
count rather than revealing anything or letting a stranger in.

So: real, bounded, and worth a rate limit on POST /groups/{id}/checkin, which
is the one mitigation this module cannot provide. See deploy/rate-limit.md.
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

# A separate domain for the typed code's HMAC, so the six digits are not a
# slice of the QR signature.
TYPED_PREFIX = "hc1t"
TYPED_DIGITS = 6


class CheckInCodeConfigurationError(RuntimeError):
    """Raised when the backend cannot securely sign check-in codes."""


@dataclass(frozen=True)
class CheckInCode:
    code: str
    # The six-digit fallback for a phone with no usable camera.
    typed: str
    # Seconds until this code stops being the current one, so the phone knows
    # when to ask for the next one rather than polling blindly.
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
    return CheckInCode(
        code=code,
        typed=_typed(student_id, window),
        expires_in=max(1, remaining),
    )


def is_typed(code: str) -> bool:
    """Whether this looks like the six-digit fallback rather than a QR payload."""
    if not isinstance(code, str) or len(code) > 200:
        return False
    candidate = _normalise_typed(code)
    return len(candidate) == TYPED_DIGITS and candidate.isdigit()


def read_typed(
    code: str,
    candidate_ids: tuple[str, ...],
    *,
    now: float | None = None,
) -> str | None:
    """Which of `candidate_ids` a typed code belongs to, or None.

    A six-digit code carries no student id, so unlike read() this cannot work
    the answer out from the code alone. The caller passes the only students it
    would ever accept, which is the members of the group being checked into,
    and the code is tried against each of them. That list is what keeps the
    search space at ten HMACs rather than the whole student table, and it is
    also what stops a code minted for one group being spent in another.
    """
    candidate = _normalise_typed(code)
    if not is_typed(candidate):
        return None

    moment = time.time() if now is None else now
    current = int(moment // CHECKIN_WINDOW_SECONDS)

    found: str | None = None
    for student_id in candidate_ids:
        for window in (current, current - 1):
            # compare_digest for the same reason read() uses it, and no early
            # return, so the time taken does not depend on which student
            # matched or how far down the list they were.
            if hmac.compare_digest(candidate, _typed(student_id, window)):
                found = student_id
    return found


def _normalise_typed(code: str) -> str:
    """Drop the spaces and dashes a student reading digits aloud will add."""
    return code.strip().replace(" ", "").replace("-", "")


def _typed(student_id: str, window: int) -> str:
    # _signing_secret(), not config.GUEST_TOKEN_SECRET: this branch reads the
    # secret in one place and refuses a short one, and the typed code has no
    # business being derivable under weaker rules than the QR payload.
    payload = f"{TYPED_PREFIX}.{student_id}.{window}"
    digest = hmac.new(_signing_secret(), payload.encode("utf-8"), sha256).hexdigest()
    return str(int(digest, 16) % (10 ** TYPED_DIGITS)).zfill(TYPED_DIGITS)


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
