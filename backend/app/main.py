"""The Hangout API.

Routes land here; the thinking lives next to it. auth.py decides who is
calling, store.py holds students, engine.py will form the groups.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from . import auth, config, presets, store
from .models import (
    DAY_NAMES,
    AhaOut,
    CreateStudentRequest,
    CreateStudentResponse,
    GapOut,
    MeResponse,
    PausedRequest,
    StudentOut,
)

# uvicorn's own logger, because it is the one with a handler attached. A
# logging.getLogger("hangout") here would drop every INFO line on the floor
# and the startup report below would silently say nothing.
log = logging.getLogger("uvicorn.error")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Say out loud which way in is open.

    The failure this prevents: deploying with neither Auth0 configured nor
    DEMO_MODE on, where every sign-in 401s and the logs show nothing but a
    healthy server.
    """
    if config.AUTH0_READY:
        log.info("auth: Auth0 ready (%s)", config.AUTH0_DOMAIN)
    if config.DEMO_MODE:
        log.info("auth: DEMO_MODE on, guest sign-in and /admin/reset available")
    if not config.AUTH0_READY and not config.DEMO_MODE:
        log.error(
            "auth: no way in. Set AUTH0_DOMAIN and AUTH0_AUDIENCE, or DEMO_MODE=true."
        )
    yield


app = FastAPI(title="Hangout API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _student_out(student: store.Student) -> StudentOut:
    return StudentOut(
        id=student.id,
        first_name=student.first_name,
        paused=student.paused,
        visibility=student.visibility,
    )


@app.get("/me", response_model=MeResponse)
def get_me(caller: Annotated[auth.Caller, Depends(auth.current_user)]) -> MeResponse:
    """Does the signed-in user have a profile?

    The route gate calls this on every app open, so it is the one request
    between the splash screen and the first real screen.

    A soft-deleted student reads as not onboarded, which is what sends them
    back through onboarding instead of showing a profile that is meant to be
    gone.
    """
    student = caller.student
    if student is None or not student.onboarded:
        return MeResponse(onboarded=False)
    return MeResponse(onboarded=True, student=_student_out(student))


@app.post("/students", response_model=CreateStudentResponse, status_code=201)
def create_student(
    body: CreateStudentRequest,
    # Deliberately the optional dependency, because a demo guest has no token
    # yet: the guest token is signed over the student row this call creates.
    caller: Annotated[auth.Caller | None, Depends(auth.current_caller)],
) -> CreateStudentResponse:
    """Create the profile at the end of onboarding.

    Calling it twice for the same identity updates the profile rather than
    making a second one, so a student who retries after a timeout does not end
    up with two accounts.
    """
    if body.guest and not config.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest sign-up is only available in demo mode.",
        )

    # No token means this can only be a demo guest asking to be one. Anything
    # else without a token is an unauthenticated write.
    if caller is None and not (config.DEMO_MODE and body.guest):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to create a profile.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    free_blocks = _resolve_blocks(body)

    student = store.upsert(
        # Always from the verified token. A guest has no token yet, so their
        # identity is minted here and handed back as guest_token below.
        auth_sub=None if caller is None else caller.auth_sub,
        is_guest=caller is None or caller.is_guest,
        first_name=body.first_name,
        tags=body.tags,
        languages=body.languages,
        ask_me_about=body.ask_me_about,
        visibility=body.visibility,
        free_blocks=free_blocks,
    )

    guest_token = None
    if caller is None:
        guest_token = auth.issue_guest_token(student.id)
        # Link the identity now that the row it names exists, so a retried
        # POST /students from this guest updates them instead of creating a
        # second student.
        store.link_sub(f"guest:{student.id}", student.id)

    return CreateStudentResponse(
        student=_student_out(student),
        aha=_aha_for(student),
        guest_token=guest_token,
    )


def _resolve_blocks(body: CreateStudentRequest) -> list[store.FreeBlock]:
    """A preset id becomes free blocks here, on the server.

    The frontend's copy of the preset list is for the labels a student reads.
    Expanding an id into hours is the server's job, so the hours the matcher
    uses cannot be edited by a request.
    """
    if body.preset_id is not None:
        blocks = presets.blocks_for(body.preset_id)
        if blocks is None:
            # The literal, not status.HTTP_422_*: Starlette renamed that
            # constant and the old name now warns on every call.
            raise HTTPException(
                status_code=422, detail=f"Unknown preset_id: {body.preset_id}"
            )
        return list(blocks)
    return [(b.day, b.start, b.end) for b in body.free_blocks or []]


@app.post("/me/paused", response_model=StudentOut)
def set_paused(
    body: PausedRequest,
    student: Annotated[store.Student, Depends(auth.onboarded_user)],
) -> StudentOut:
    """Pause or resume matching.

    A privacy setting, not a preference: while paused the student is in no
    group the optimizer forms, which is why the Right now screen says so
    rather than looking empty.
    """
    updated = store.set_paused(student.id, body.paused)
    return _student_out(updated or student)


@app.post("/admin/reset")
def admin_reset() -> dict[str, bool]:
    """Re-run the seed. Demo mode only, and 404 otherwise, so the production
    deployment does not advertise that the route exists."""
    if not config.DEMO_MODE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    store.reset()
    return {"ok": True}


# ------------------------------------------------------------------ the number


def _aha_for(student: store.Student) -> AhaOut | None:
    """One honest, non-zero number, or nothing.

    Next gap first, because that is the one they can act on today. If nobody
    shares it, the busiest gap they have, because a new student being told
    "0 people are free when you are" is the worst thing this app can say.
    If even that is zero, return None and the frontend skips the screen rather
    than printing a zero.
    """
    if not student.free_blocks:
        return None

    block = _next_block(student.free_blocks)
    free_count = store.overlap_count(block, student.id)

    if free_count == 0:
        busiest = store.busiest_block(student)
        if busiest is not None:
            block = busiest
            free_count = store.overlap_count(block, student.id)

    if free_count == 0:
        return None

    tag = student.tags[0] if student.tags else None
    same_tag = 0 if tag is None else store.overlap_count_with_tag(block, tag, student.id)

    day, start, end = block
    return AhaOut(
        gap=GapOut(day=DAY_NAMES[day], start=_hhmm(start), end=_hhmm(end)),
        free_count=free_count,
        same_tag_count=same_tag,
        tag=tag,
    )


def _next_block(blocks: list[store.FreeBlock], now: datetime | None = None) -> store.FreeBlock:
    """The gap that comes up soonest, wrapping into next week.

    Sorting by "days from today, then start time" means Thursday reads as
    sooner than Monday when today is Wednesday, which is what a student
    expects from the words "your next gap".
    """
    moment = now or datetime.now()
    today = moment.weekday()
    current = moment.time()

    def distance(block: store.FreeBlock) -> tuple[int, time]:
        day, start, _end = block
        days = (day - today) % 7
        if days == 0 and start <= current:
            days = 7
        return days, start

    return min(blocks, key=distance)


def _hhmm(value: time) -> str:
    return value.strftime("%H:%M")
