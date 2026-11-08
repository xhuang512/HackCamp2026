"""Check-in codes.

AGENTS.md: each joined member's phone shows a group code, the backend signs
it, it changes every 30 seconds, and it only validates between members of the
same group. Scanning a groupmate's code checks both people in. There are no
building QR codes.

The code is a string small enough to be a QR payload and short enough to read
out loud as a fallback when a phone refuses the camera:

    hc1.<student_id>.<window>.<signature>

The group id is not in the payload. It comes from the URL the code is posted
to, and the backend checks that both students are members of that group. That
is what stops a code from one group being replayed into another.

`window` is the 30-second slot the code was minted in, so a screenshot stops
working almost immediately. Verification accepts the current slot and the one
before it, because a scan takes a moment and a code that expires between
being shown and being read is a code that never works on stage.
"""

import hmac
import time
from dataclasses import dataclass
from hashlib import sha256

from . import config
from .constants import CHECKIN_WINDOW_SECONDS

PREFIX = "hc1"

# Enough signature to make guessing hopeless, short enough to keep the QR
# code readable by a cheap phone camera at arm's length. 16 hex characters is
# 64 bits.
_SIGNATURE_CHARS = 16


@dataclass(frozen=True)
class CheckInCode:
    code: str
    # Seconds until this code stops being the current one, so the phone knows
    # when to ask for the next one rather than polling blindly.
    expires_in: int


def issue(student_id: str, *, now: float | None = None) -> CheckInCode:
    """The caller's current code. Rotates every CHECKIN_WINDOW_SECONDS."""
    moment = time.time() if now is None else now
    window = int(moment // CHECKIN_WINDOW_SECONDS)
    code = f"{PREFIX}.{student_id}.{window}.{_sign(student_id, window)}"
    used = moment % CHECKIN_WINDOW_SECONDS
    return CheckInCode(code=code, expires_in=int(CHECKIN_WINDOW_SECONDS - used) or 1)


def read(code: str, *, now: float | None = None) -> str | None:
    """The student id a code names, or None if it is not a valid current one.

    None covers every way a code can be wrong: the wrong shape, a bad
    signature, or a window too old to accept. The caller does not get to know
    which, because telling a scanner why its forgery failed helps nobody.
    """
    parts = code.strip().split(".")
    if len(parts) != 4 or parts[0] != PREFIX:
        return None
    _, student_id, raw_window, signature = parts
    try:
        window = int(raw_window)
    except ValueError:
        return None

    # compare_digest, not ==, so a wrong signature takes the same time to
    # reject however many leading characters it got right.
    if not hmac.compare_digest(signature, _sign(student_id, window)):
        return None

    moment = time.time() if now is None else now
    current = int(moment // CHECKIN_WINDOW_SECONDS)
    if window not in (current, current - 1):
        return None
    return student_id


def _sign(student_id: str, window: int) -> str:
    payload = f"{PREFIX}.{student_id}.{window}"
    return hmac.new(
        config.GUEST_TOKEN_SECRET.encode(), payload.encode(), sha256
    ).hexdigest()[:_SIGNATURE_CHARS]
