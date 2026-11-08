"""Check-in codes.

AGENTS.md: each joined member's phone shows a group code, the backend signs
it, it changes every 30 seconds, and it only validates between members of the
same group. Scanning a groupmate's code checks both people in. There are no
building QR codes.

Every code comes in two forms, for two different readers.

The QR payload, which nobody types:

    hc1.<student_id>.<window>.<signature>

And a six-digit typed code for the fallback, when a phone has no working
camera:

    482716

The typed form is the weaker of the two and is deliberately not a truncation
of the signature above: it is a separate HMAC over a different payload, so
reading one off a screen tells you nothing about the other. Six digits is
about 20 bits against the QR payload's 64. What keeps it usable is everything
around it. It rotates every 30 seconds, it is only accepted from a caller who
has already joined the group, it only matches a member of that same group,
and the route tries it against that group's members alone, which is at most
five people over two time windows. A guess is therefore worth roughly ten
chances in a million for the 30 seconds it stays current.

That is fine for a code read out across a table and would not be fine as the
only check-in mechanism.

What a guessing attack actually costs, because the bare bit count makes it
sound worse than it is. The endpoint needs a valid session AND membership of
the group being guessed at, so the attacker is already inside the group. At
ten chances in a million per try, even odds take about 70,000 requests inside
the 60 seconds a code stays acceptable. And the prize is a false check-in for
someone who is already a groupmate, which inflates the hangout count rather
than revealing anything or letting a stranger in.

So: real, bounded, and worth a rate limit on POST /groups/{id}/checkin, which
is the one mitigation the code itself cannot provide. Not built here, because
a limiter belongs in the serving layer. Recorded in docs/design-report.md.

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
# A separate domain for the typed code's HMAC, so the six digits are not a
# slice of the QR signature.
TYPED_PREFIX = "hc1t"
TYPED_DIGITS = 6

# Enough signature to make guessing hopeless, short enough to keep the QR
# code readable by a cheap phone camera at arm's length. 16 hex characters is
# 64 bits.
_SIGNATURE_CHARS = 16


@dataclass(frozen=True)
class CheckInCode:
    code: str
    # The six-digit fallback for a phone with no usable camera.
    typed: str
    # Seconds until this code stops being the current one, so the phone knows
    # when to ask for the next one rather than polling blindly.
    expires_in: int


def issue(student_id: str, *, now: float | None = None) -> CheckInCode:
    """The caller's current code. Rotates every CHECKIN_WINDOW_SECONDS."""
    moment = time.time() if now is None else now
    window = int(moment // CHECKIN_WINDOW_SECONDS)
    code = f"{PREFIX}.{student_id}.{window}.{_sign(student_id, window)}"
    used = moment % CHECKIN_WINDOW_SECONDS
    return CheckInCode(
        code=code,
        typed=_typed(student_id, window),
        expires_in=int(CHECKIN_WINDOW_SECONDS - used) or 1,
    )


def is_typed(code: str) -> bool:
    """Whether this looks like the six-digit fallback rather than a QR payload."""
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
    payload = f"{TYPED_PREFIX}.{student_id}.{window}"
    digest = hmac.new(
        config.GUEST_TOKEN_SECRET.encode(), payload.encode(), sha256
    ).hexdigest()
    return str(int(digest, 16) % (10 ** TYPED_DIGITS)).zfill(TYPED_DIGITS)


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
