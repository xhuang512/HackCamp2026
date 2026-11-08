"""Identity: who you are, and whether you have a profile yet.

Lifted out of the signup branch's main.py when the two backends merged. The
routes and their reasoning are unchanged; only the decorators moved from the
app to a router so main.py stays a wiring file.

These four run on store.py, the in-memory student store, while the group,
matching and projector routes run on the Supabase repositories. That split is
deliberate and temporary: schema.sql already has auth_sub, onboarded, paused
and visibility, but no repository reads them yet. Porting these routes is one
job, and it does not change their signatures.
"""

import logging
import os
from datetime import datetime, time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from .. import auth, config, presets, store
from ..badges import badges_for
from ..db import get_db_client
from ..matching import next_matching_dates, run_matching
from ..repositories import ReferenceDataError, RepositoryError
from ..repositories.free_blocks import FreeBlockInput, FreeBlockRepository
from ..repositories.group_members import GroupMemberRepository
from ..repositories.reference_data import normalize_course_codes
from ..repositories.students import StudentRepository
from ..models import (
    DAY_NAMES,
    MAX_FAVOURITE_SPOTS,
    AhaOut,
    CreateStudentRequest,
    CreateStudentResponse,
    GapOut,
    MeResponse,
    PatchMeRequest,
    PausedRequest,
    StudentOut,
)
from ..repositories.buildings import BuildingRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["identity"])


def _student_out(student: store.Student) -> StudentOut:
    return StudentOut(
        id=student.id,
        first_name=student.first_name,
        is_guest=student.is_guest,
        paused=student.paused,
        visibility=student.visibility,
        tags=student.tags,
        favourite_spots=student.favourite_spots,
    )


def _mirror(
    client: Client,
    student: store.Student,
    *,
    spots: list[str] | None = None,
) -> None:
    """Copy identity onto the Supabase row the matcher reads.

    This is the fix for the one privacy rule the merge broke. Identity lives
    in store.py, in memory, while StudentRepository.list_matchable() filters
    the Supabase `paused` column, which nothing wrote after signup. So a
    student who tapped pause kept being formed into groups, and AGENTS.md
    says pause and visibility are always respected by matching.

    A failed mirror is logged and swallowed on purpose. The alternative is a
    500 on a Me tab toggle, which would leave the student unsure whether they
    are paused. The in-memory flag is already set and the next write retries.
    """
    try:
        students = StudentRepository(client)
        students.update_profile(
            student.id,
            first_name=student.first_name,
            paused=student.paused,
            visibility=student.visibility,
        )
        if spots is not None:
            students.set_spots(student.id, _spot_ids(client, spots))
    except RepositoryError:
        logger.exception("Could not mirror student %s into Supabase", student.id)


def _spot_ids(client: Client, slugs: list[str]) -> list[int]:
    """Building slugs to ids, in the order given, unknown slugs rejected."""
    buildings = {
        str(row["slug"]): int(row["id"]) for row in BuildingRepository(client).list_all()
    }
    unknown = [slug for slug in slugs if slug not in buildings]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown building slugs: {', '.join(unknown)}"
        )
    return [buildings[slug] for slug in slugs]

@router.get("/me", response_model=MeResponse)
def get_me(
    caller: Annotated[auth.Caller, Depends(auth.current_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> MeResponse:
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
    try:
        badges = badges_for(
            student.id,
            GroupMemberRepository(client).list_for_student(student.id),
        )
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load profile badges",
        ) from exc
    return MeResponse(onboarded=True, student=_student_out(student), badges=badges)

@router.post("/students", response_model=CreateStudentResponse, status_code=201)
def create_student(
    body: CreateStudentRequest,
    # Deliberately the optional dependency, because a demo guest has no token
    # yet: the guest token is signed over the student row this call creates.
    caller: Annotated[auth.Caller | None, Depends(auth.current_caller)],
    client: Annotated[Client, Depends(get_db_client)],
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

    # Supabase first, because it is the side that validates the request and
    # the side that mints the id. Both stores then use that one id, so the
    # student GET /me reads out of store.py and the student GET /me/now reads
    # out of Supabase are the same student.
    existing = None if caller is None else store.get_by_sub(caller.auth_sub)
    student_id = _persist_matchable(client, body, free_blocks, existing)

    student = store.put(
        store.Student(
            id=student_id,
            first_name=body.first_name,
            # Always from the verified token. A guest has no token yet, so
            # their identity is minted here and handed back as guest_token
            # below.
            auth_sub=None if caller is None else caller.auth_sub,
            is_guest=caller is None or caller.is_guest,
            tags=body.tags,
            languages=body.languages,
            ask_me_about=body.ask_me_about,
            visibility=body.visibility,
            favourite_spots=body.favourite_spots,
            free_blocks=free_blocks,
        )
    )

    if body.favourite_spots:
        _mirror(client, student, spots=body.favourite_spots)

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

@router.patch("/me", response_model=StudentOut)
def patch_me(
    body: PatchMeRequest,
    student: Annotated[store.Student, Depends(auth.onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> StudentOut:
    """Update name, tags, visibility, favourite spots and paused.

    Partial by design: the Me tab sends the one thing the student changed.
    Everything that reaches here also reaches the Supabase row, because
    pause and visibility are matching rules and the matcher reads that table.
    """
    if body.favourite_spots is not None and len(body.favourite_spots) > MAX_FAVOURITE_SPOTS:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_FAVOURITE_SPOTS} favourite spots",
        )

    updated = (
        store.update(
            student.id,
            first_name=body.first_name,
            tags=body.tags,
            languages=body.languages,
            ask_me_about=body.ask_me_about,
            visibility=body.visibility,
            favourite_spots=body.favourite_spots,
            paused=body.paused,
        )
        or student
    )
    _mirror(client, updated, spots=body.favourite_spots)
    return _student_out(updated)


@router.post("/me/paused", response_model=StudentOut)
def set_paused(
    body: PausedRequest,
    student: Annotated[store.Student, Depends(auth.onboarded_user)],
    client: Annotated[Client, Depends(get_db_client)],
) -> StudentOut:
    """Pause or resume matching.

    A privacy setting, not a preference: while paused the student is in no
    group the optimizer forms, which is why the Right now screen says so
    rather than looking empty.

    PATCH /me does this and more. This route stays because it is already
    merged and the paused banner calls it, and it is now a thin alias so the
    two cannot drift.
    """
    updated = store.set_paused(student.id, body.paused)
    student = updated or student
    _mirror(client, student)
    return _student_out(student)

@router.get("/auth/config")
def auth_config() -> dict[str, object]:
    """What this server thinks it is configured for.

    Purely a setup aid, for working through the Auth0 checklist in
    docs/SIGNUP.md with curl instead of a phone. It exposes nothing private:
    the domain and the audience are both already compiled into the public
    frontend bundle, and the secrets are reported as set or unset, never read
    back.
    """
    return {
        "demo_mode": config.DEMO_MODE,
        "guest_token_secret_set": bool(os.getenv("GUEST_TOKEN_SECRET")),
        "auth0": {
            "configured": config.AUTH0_READY,
            "domain": config.AUTH0_DOMAIN,
            "audience": config.AUTH0_AUDIENCE,
            "problem": auth.check_auth0_reachable(),
        },
    }

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


# ------------------------------------------------- the Supabase half


def _persist_matchable(
    client: Client,
    body: CreateStudentRequest,
    free_blocks: list[store.FreeBlock],
    existing: store.Student | None,
) -> str:
    """Write the student the matcher can see, and return the id both stores use.

    Identity lives in store.py and matching lives in Supabase, so a signup has
    to land in both or the student gets an aha number and then never gets a
    group. This is the dual write that keeps them together until identity
    moves to Supabase too.

    Validation errors are the caller's fault and surface as 422. A Supabase
    failure is not, so the row is rolled back and the signup fails rather than
    leaving a student who exists in memory and nowhere else.
    """
    term = os.getenv("CURRENT_TERM")
    if body.courses and not term:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CURRENT_TERM is required to persist student courses",
        )
    try:
        course_codes = normalize_course_codes(body.courses)
    except ReferenceDataError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # A second signup from the same identity updates the profile. The
    # matchable row already exists, so re-creating it would make a duplicate
    # student the optimizer could put in two groups.
    if existing is not None:
        return existing.id

    students = StudentRepository(client)
    blocks = tuple(
        FreeBlockInput(
            day=day,
            # "HH:MM", matching the format the existing preset blocks and
            # the matcher already use. Postgres accepts either, but mixed
            # formats in one column are a trap for anything comparing them
            # as strings.
            start_time=start.strftime("%H:%M"),
            end_time=end.strftime("%H:%M"),
        )
        for day, start, end in free_blocks
    )

    created: dict[str, Any] | None = None
    try:
        created = students.create(body.first_name)
        student_id = str(created["id"])
        students.add_tags(student_id, body.tags)
        students.add_languages(student_id, body.languages)
        students.add_courses(student_id, course_codes, term or "")
        FreeBlockRepository(client).create_for_student(student_id, blocks)
    except ReferenceDataError as exc:
        _rollback(students, created)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RepositoryError as exc:
        _rollback(students, created)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not persist student onboarding",
        ) from exc

    for target_date in next_matching_dates({block.day for block in blocks}):
        try:
            run_matching(client, target_date, persist=True)
        except RepositoryError:
            # Onboarding has already succeeded. A later signup or the batch
            # CLI can retry this student without forcing them to register
            # again.
            logger.exception(
                "Automatic matching failed after creating student %s for %s",
                student_id,
                target_date,
            )
    return student_id


def _rollback(repository: StudentRepository, created: dict[str, Any] | None) -> None:
    """Undo a half-written signup so a 422 leaves no student behind."""
    if created is None or "id" not in created:
        return
    try:
        repository.delete(str(created["id"]))
    except RepositoryError:
        # Keep the original error. The service-role logs retain the cause.
        logger.exception("Could not roll back student %s", created.get("id"))
