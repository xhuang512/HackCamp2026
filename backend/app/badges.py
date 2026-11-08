"""Badges derived from check-ins, with no ledger that can drift.

Nothing is stored. Every badge is recomputed from the caller's own
group_members rows, so a badge cannot be awarded twice, cannot be lost to a
failed write, and cannot disagree with the hangouts it claims to count.

The four badges are the Campus Cat set from the design file. What earns each
one is NOT in that file, so the thresholds here are ours, chosen from data
the backend actually holds.

One honest limit, stated because the names oversell what is measured. There
is no record of who started a group: `groups` has no created_by column and a
founder's membership row is indistinguishable from anyone else's. So the two
Host badges count hangouts attended rather than hosted. Making them literal
needs one nullable column and a line in POST /groups; until then these are
participation tiers wearing host names.
"""

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.models import BadgeOut, BadgeProgress, TopBadgeOut

# What a badge counts.
TOTAL = "total"
STUDY = "study"
SOCIAL = "social"


@dataclass(frozen=True)
class BadgeDefinition:
    slug: str
    name: str
    checkins: int
    # Which check-ins count: all of them, or only those at a group of one
    # mode. The mode ones need `modes` passed to badges_for; without it they
    # stay locked rather than guessing.
    counts: str = TOTAL


# Ordered easiest first. top_badge() takes the last earned, so this order is
# also the ranking a group card shows.
BADGES = (
    BadgeDefinition("community_host", "Community Host", 1),
    BadgeDefinition("social_regular", "Social Regular", 3, counts=SOCIAL),
    BadgeDefinition("study_regular", "Study Regular", 3, counts=STUDY),
    BadgeDefinition("super_host", "Super Host", 5),
)


def badges_for(
    student_id: str,
    memberships: Iterable[Mapping[str, Any]],
    modes: Mapping[str, str] | None = None,
) -> list[BadgeOut]:
    """Every badge and its progress for one student's arrived rows.

    `modes` maps a group id to 'social' or 'study'. It is optional because
    not every caller has the groups in hand, and a caller without it gets the
    mode badges locked rather than a number that counts the wrong thing.
    """
    attended = [
        member
        for member in memberships
        if str(member.get("student_id")) == student_id
        and member.get("arrived_at") is not None
    ]

    counts = {
        TOTAL: len(attended),
        STUDY: 0,
        SOCIAL: 0,
    }
    if modes is not None:
        for member in attended:
            mode = modes.get(str(member.get("group_id")))
            if mode in (STUDY, SOCIAL):
                counts[mode] += 1

    return [
        BadgeOut(
            slug=badge.slug,
            name=badge.name,
            earned=counts[badge.counts] >= badge.checkins,
            progress=BadgeProgress(
                current=min(counts[badge.counts], badge.checkins),
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
