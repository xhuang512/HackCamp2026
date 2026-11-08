"""Settings, read once at import.

DEMO_MODE is the one flag that changes behaviour rather than wiring. The same
code is deployed twice, once with it on for the stage:

  * guest sign-in works and POST /students will issue a guest token
  * POST /admin/reset exists and re-runs the seed

Everything it enables is additive, so the production deployment is the plain
one and nothing has to be removed before the demo.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


DEMO_MODE = _flag("DEMO_MODE", default=True)

# Auth0. Unset means passwordless email sign-in is not available yet, and
# current_user() accepts guest tokens only. A deployment with neither
# DEMO_MODE nor these set has no way in at all, which main.py reports at
# startup rather than failing one request at a time.
AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE")
AUTH0_ALGORITHMS = ["RS256"]

AUTH0_READY = bool(AUTH0_DOMAIN and AUTH0_AUDIENCE)

# Signs guest tokens and check-in codes. Generated per process when unset,
# so restarting the server invalidates every guest session. That is fine for
# a demo and wrong for anything else, which is why a deployed instance should
# set it.
#
# GUEST_SESSION_SECRET is the name the team's .env and the tests already use.
# Reading both means a secret that is set is actually used, instead of being
# silently ignored in favour of a fresh random value on every restart.
GUEST_TOKEN_SECRET = (
    os.getenv("GUEST_TOKEN_SECRET")
    or os.getenv("GUEST_SESSION_SECRET")
    or os.urandom(32).hex()
)

# How long a guest session lasts. A stage demo is minutes, not days, and a
# guest profile is disposable.
GUEST_TOKEN_HOURS = int(os.getenv("GUEST_TOKEN_HOURS", "12"))

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
