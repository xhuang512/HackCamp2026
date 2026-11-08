"""Where students live.

The walking skeleton's dumbest body behind its final interface. Every function
here has the signature it will keep; the bodies hold rows in a dict instead of
Postgres. Swapping in Supabase is this one file, and no caller changes.

What that costs, stated plainly so nobody is surprised:

  * Everything is lost on restart, including real signups.
  * One process only. Two workers do not share students.

So this is for local development and the stage demo. Before anything real,
replace the bodies with Supabase queries against backend/schema.sql, which
already has every table these functions pretend to be.

The seed students at the bottom are here for the same reason: the aha screen's
promise is one honest, non-zero number, and an empty store cannot make one.
They move to seed.py once there is a database to seed.
"""

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from .presets import PRESETS

FreeBlock = tuple[int, time, time]


@dataclass
class Student:
    id: str
    first_name: str
    auth_sub: str | None = None
    is_guest: bool = False
    is_seed: bool = False
    ask_me_about: str | None = None
    visibility: str = "everyone"
    paused: bool = False
    tags: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    # Building slugs, best first, at most three. Feeds engine.pick_spot.
    favourite_spots: list[str] = field(default_factory=list)
    free_blocks: list[FreeBlock] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deleted_at: datetime | None = None

    @property
    def onboarded(self) -> bool:
        """A soft-deleted student counts as not onboarded, so they are offered
        onboarding again rather than shown a profile that is meant to be
        gone."""
        return self.deleted_at is None


_students: dict[str, Student] = {}
# auth_sub -> student id. The lookup current_user() does on every request.
_by_sub: dict[str, str] = {}


# ---------------------------------------------------------------- reads


def get(student_id: str) -> Student | None:
    return _students.get(student_id)


def get_by_sub(auth_sub: str) -> Student | None:
    student_id = _by_sub.get(auth_sub)
    return None if student_id is None else _students.get(student_id)


def overlap_count(block: FreeBlock, exclude_id: str | None = None) -> int:
    """How many other students are free during some part of `block`.

    The one number the aha screen shows. It counts people, never names them,
    and it skips paused students because matching skips them too: a count that
    includes someone the matcher will never offer is a lie.
    """
    day, start, end = block
    total = 0
    for student in _students.values():
        if student.id == exclude_id or student.paused or not student.onboarded:
            continue
        if any(
            b_day == day and b_start < end and b_end > start
            for b_day, b_start, b_end in student.free_blocks
        ):
            total += 1
    return total


def overlap_count_with_tag(
    block: FreeBlock, tag: str, exclude_id: str | None = None
) -> int:
    """Of those, how many share one tag with the student."""
    day, start, end = block
    total = 0
    for student in _students.values():
        if student.id == exclude_id or student.paused or not student.onboarded:
            continue
        if tag not in student.tags:
            continue
        if any(
            b_day == day and b_start < end and b_end > start
            for b_day, b_start, b_end in student.free_blocks
        ):
            total += 1
    return total


def busiest_block(student: Student) -> FreeBlock | None:
    """The student's gap that the most other students share.

    The aha screen falls back to this when nobody shares the next gap, because
    "0 people are free when you are" is the worst thing the app can say to
    someone who just finished signing up.
    """
    if not student.free_blocks:
        return None
    return max(student.free_blocks, key=lambda b: overlap_count(b, student.id))


# ---------------------------------------------------------------- writes


def upsert(
    *,
    auth_sub: str | None,
    is_guest: bool,
    first_name: str,
    tags: list[str],
    languages: list[str],
    ask_me_about: str | None,
    visibility: str,
    free_blocks: list[FreeBlock],
) -> Student:
    """Create the profile, or update it if this identity already has one.

    `auth_sub` comes from the verified token and never from a request body, so
    this cannot be used to create a profile for somebody else. Calling it
    twice for the same identity updates rather than making a second student,
    which is what makes a retried POST /students safe.
    """
    existing = None if auth_sub is None else get_by_sub(auth_sub)

    student = existing or Student(id=str(uuid.uuid4()), first_name=first_name)
    student.first_name = first_name
    student.auth_sub = auth_sub
    student.is_guest = is_guest
    student.tags = tags
    student.languages = languages
    student.ask_me_about = ask_me_about
    student.visibility = visibility
    student.free_blocks = free_blocks
    # Signing up again after deleting an account un-deletes it.
    student.deleted_at = None

    _students[student.id] = student
    if auth_sub is not None:
        _by_sub[auth_sub] = student.id
    return student


def put(student: Student) -> Student:
    """Insert or replace a student by id, linking its auth_sub if it has one.

    For seeds and tests, which need a student with a known id. upsert() mints
    a fresh uuid, so it cannot be used to place a student that a token has
    already been signed for.
    """
    _students[student.id] = student
    if student.auth_sub is not None:
        _by_sub[student.auth_sub] = student.id
    return student


def link_sub(auth_sub: str, student_id: str) -> None:
    """Point an identity at an existing student.

    A guest's identity does not exist until their student row does: the token
    is signed over the row's id. So the row is created first and linked here,
    which is what makes a second POST /students from the same guest update
    that student instead of creating another one.
    """
    student = _students.get(student_id)
    if student is None:
        return
    student.auth_sub = auth_sub
    _by_sub[auth_sub] = student_id


def set_paused(student_id: str, paused: bool) -> Student | None:
    student = _students.get(student_id)
    if student is None:
        return None
    student.paused = paused
    return student


def update(student_id: str, **changes: object) -> Student | None:
    """Apply only the fields a PATCH actually sent.

    None means "leave it alone", so a Me tab that toggles pause cannot blank
    the student's tags on the way past. Unknown field names are ignored
    rather than setting stray attributes on the row.
    """
    student = _students.get(student_id)
    if student is None:
        return None
    for name, value in changes.items():
        if value is None or not hasattr(student, name):
            continue
        setattr(student, name, value)
    return student


def reset() -> None:
    """Drop every student and recreate the seeds. Real signups do not survive
    this, which the Postgres version fixes by deleting only is_seed rows."""
    _students.clear()
    _by_sub.clear()
    _install_seeds()


# ---------------------------------------------------------------- seeds

_SEED_NAMES = [
    "Ji-woo", "Amir", "Rosa", "Wei", "Noor", "Dev", "Mina", "Tomas",
    "Aisha", "Kenji", "Lucia", "Omar", "Priya", "Yuki", "Hana", "Luc",
    "Sana", "Diego", "Mei", "Arjun", "Zara", "Theo", "Nadia", "Ravi",
]
_SEED_TAGS = ["international", "transfer", "exchange", "commuter", "first-year", "grad"]
_SEED_LANGUAGES = ["en", "zh", "yue", "ko", "ja", "pa", "hi", "fa", "es", "fr"]


def _install_seeds(count: int = 90) -> None:
    """Fake students, spread evenly over the presets so no preset is a dead
    end. Seeded random, so the demo tells the same story twice."""
    rng = random.Random(2026)
    preset_ids = list(PRESETS)

    for i in range(count):
        preset_id = preset_ids[i % len(preset_ids)]
        tags = rng.sample(_SEED_TAGS, k=rng.choice([1, 1, 2]))
        student_id = str(uuid.uuid4())
        _students[student_id] = Student(
            id=student_id,
            first_name=_SEED_NAMES[i % len(_SEED_NAMES)],
            is_seed=True,
            tags=tags,
            languages=rng.sample(_SEED_LANGUAGES, k=rng.choice([1, 2])),
            free_blocks=list(PRESETS[preset_id]),
        )


_install_seeds()
