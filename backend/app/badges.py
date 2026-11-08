"""Badges derived from check-ins, with no ledger that can drift.

A badge is earned by counting the student's group_members rows that have
arrived_at set. That column is only written by the QR check-in RPC
(check_in_group_members), and (group_id, student_id) is the primary key, so
each meetup counts once however many times the pair rescans. Nothing is
stored, so there is nothing to award twice.

Names and thresholds come from origin/feat/badges.
"""

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.models import BadgeOut, BadgeProgress, TopBadgeOut


@dataclass(frozen=True)
class BadgeDefinition:
    slug: str
    name: str
    checkins: int

    @property
    def description(self) -> str:
        if self.checkins == 1:
            return "Check in at your first meetup."
        return f"Check in at {self.checkins} meetups."


BADGES = (
    BadgeDefinition("first_hello", "First Hello", 1),
    BadgeDefinition("regular", "Regular", 3),
    BadgeDefinition("familiar_face", "Familiar Face", 5),
)


def checkin_count(
    student_id: str,
    memberships: Iterable[Mapping[str, Any]],
) -> int:
    return sum(
        str(member.get("student_id")) == student_id
        and member.get("arrived_at") is not None
        for member in memberships
    )


def badges_for(
    student_id: str,
    memberships: Iterable[Mapping[str, Any]],
) -> list[BadgeOut]:
    """Return every badge and progress for one student's arrived rows."""
    checkins = checkin_count(student_id, memberships)
    return [
        BadgeOut(
            slug=badge.slug,
            name=badge.name,
            description=badge.description,
            earned=checkins >= badge.checkins,
            progress=BadgeProgress(
                current=min(checkins, badge.checkins),
                target=badge.checkins,
            ),
        )
        for badge in BADGES
    ]


def top_badge(badges: Iterable[BadgeOut]) -> TopBadgeOut | None:
    earned = [badge for badge in badges if badge.earned]
    if not earned:
        return None
    badge = earned[-1]
    return TopBadgeOut(slug=badge.slug, name=badge.name)


def newly_earned_badges(
    before: Iterable[BadgeOut],
    after: Iterable[BadgeOut],
) -> list[TopBadgeOut]:
    earned_before = {badge.slug for badge in before if badge.earned}
    return [
        TopBadgeOut(slug=badge.slug, name=badge.name)
        for badge in after
        if badge.earned and badge.slug not in earned_before
    ]
