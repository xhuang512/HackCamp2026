"""The Hangout API.

Routes land here; the thinking lives next to them. auth.py decides who is
calling, the routers hold the endpoints, engine.py and matching.py form the
groups.

Two stores, on purpose and not for long. Identity and onboarding run on
store.py, in memory. Groups, matching, reference data and the projector run on
the Supabase repositories. schema.sql already has the identity columns; no
repository reads them yet, so moving the identity routes over is a contained
job that does not change any route signature.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import auth, config
from app.routers import (
    admin,
    groups,
    identity,
    options,
    projector,
    schedule,
    students,
)
# Aliased: the module is app/routers/map.py and a bare `map` here would
# shadow the builtin for the rest of this file.
from app.routers import map as map_router

# backend/.env, not the repository root. parents[2] pointed at a file that
# does not exist, so this load did nothing and the backend only found its
# settings because config.py calls load_dotenv() from the working
# directory. That made "it works" depend on being started from backend/.
ROOT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

# uvicorn's own logger, because it is the one with a handler attached. A
# logging.getLogger("hangout") here would drop every INFO line on the floor
# and the startup report below would silently say nothing.
log = logging.getLogger("uvicorn.error")


def parse_cors_origins(value: str) -> list[str]:
    origins = list(
        dict.fromkeys(
            origin.strip().rstrip("/")
            for origin in value.split(",")
            if origin.strip()
        )
    )
    if not origins:
        raise RuntimeError("CORS_ORIGINS must contain at least one frontend origin")
    for origin in origins:
        parsed = urlsplit(origin)
        if origin == "*":
            raise RuntimeError(
                "CORS_ORIGINS cannot contain '*' when credentials are enabled"
            )
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError(
                f"Invalid CORS origin '{origin}'; use an exact http(s) origin"
            )
    return origins


load_dotenv(ROOT_ENV_FILE, override=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Say out loud which way in is open.

    The failure this prevents: deploying with neither Auth0 configured nor
    DEMO_MODE on, where every sign-in 401s and the logs show nothing but a
    healthy server.
    """
    if config.AUTH0_READY:
        problem = auth.check_auth0_reachable()
        if problem is None:
            log.info("auth: Auth0 ready (%s)", config.AUTH0_DOMAIN)
        else:
            log.error("auth: Auth0 configured but unusable, %s", problem)
    if config.DEMO_MODE:
        log.info("auth: DEMO_MODE on, guest sign-in and /admin/reset available")
    if not config.AUTH0_READY and not config.DEMO_MODE:
        log.error(
            "auth: no way in. Set AUTH0_DOMAIN and AUTH0_AUDIENCE, or DEMO_MODE=true."
        )
    yield


app = FastAPI(title="Hangout API", lifespan=lifespan)

# CORS_ORIGINS is validated; config.ALLOWED_ORIGINS is the signup branch's
# plainer reader of the same idea. The validated one wins, and falls back to
# ALLOWED_ORIGINS so an existing backend/.env keeps working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_origins(
        os.getenv("CORS_ORIGINS")
        or os.getenv("ALLOWED_ORIGINS")
        or DEFAULT_CORS_ORIGINS
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# identity first: it owns POST /students and GET /me, which every other
# screen depends on having happened.
app.include_router(identity.router)
app.include_router(students.router)
app.include_router(schedule.router)
app.include_router(options.router)
app.include_router(groups.router)
app.include_router(map_router.router)
app.include_router(projector.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
