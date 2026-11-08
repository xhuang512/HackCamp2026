from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from app.constants import MIN_GROUP_SIZE



class GroupStatus(StrEnum):
    FORMING = "forming"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    DISSOLVED = "dissolved"


class InvitationStatus(StrEnum):
    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class AttendanceStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    CHECKED_IN = "checked_in"
    NO_SHOW = "no_show"


class InvalidLifecycleTransition(ValueError):
    """Raised when a group or invitation transition violates lifecycle rules."""


@dataclass(frozen=True)
class GroupLifecycle:
    status: GroupStatus
    invitation_deadline: datetime
    meeting_start: datetime
    meeting_end: datetime
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        timestamps = (
            self.invitation_deadline,
            self.meeting_start,
            self.meeting_end,
        )
        if any(value.tzinfo is None or value.utcoffset() is None for value in timestamps):
            raise ValueError("group lifecycle timestamps must be timezone-aware")
        if self.invitation_deadline > self.meeting_start:
            raise ValueError("invitation deadline cannot be after the meeting starts")
        if self.meeting_start >= self.meeting_end:
            raise ValueError("meeting end must be after meeting start")


@dataclass(frozen=True)
class MembershipLifecycle:
    student_id: str
    invitation_status: InvitationStatus = InvitationStatus.INVITED
    checked_in_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.checked_in_at is not None and self.invitation_status != InvitationStatus.ACCEPTED:
            raise ValueError("only an accepted member can have a check-in timestamp")
        if self.checked_in_at is not None and (
            self.checked_in_at.tzinfo is None
            or self.checked_in_at.utcoffset() is None
        ):
            raise ValueError("check-in timestamp must be timezone-aware")


@dataclass(frozen=True)
class LifecycleUpdate:
    group: GroupLifecycle
    memberships: tuple[MembershipLifecycle, ...]

    @property
    def accepted_count(self) -> int:
        return accepted_member_count(self.memberships)


_ALLOWED_GROUP_TRANSITIONS: dict[GroupStatus, frozenset[GroupStatus]] = {
    GroupStatus.FORMING: frozenset({GroupStatus.CONFIRMED, GroupStatus.DISSOLVED}),
    GroupStatus.CONFIRMED: frozenset({GroupStatus.ACTIVE}),
    GroupStatus.ACTIVE: frozenset({GroupStatus.COMPLETED}),
    GroupStatus.COMPLETED: frozenset(),
    GroupStatus.DISSOLVED: frozenset(),
}


def transition_group(
    group: GroupLifecycle,
    target: GroupStatus,
    *,
    at: datetime,
    accepted_count: int,
) -> GroupLifecycle:
    """Apply one validated group-state transition.

    Repeating the current state is idempotent. Catch-up across multiple states is
    handled by ``advance_group_for_time`` rather than by skipping transitions.
    """
    _require_aware(at, "transition timestamp")
    if target == group.status:
        return group
    if target not in _ALLOWED_GROUP_TRANSITIONS[group.status]:
        raise InvalidLifecycleTransition(
            f"cannot transition group from {group.status} to {target}"
        )
    if target == GroupStatus.CONFIRMED and accepted_count < MIN_GROUP_SIZE:
        raise InvalidLifecycleTransition(
            f"confirmation requires {MIN_GROUP_SIZE} accepted members"
        )
    if target == GroupStatus.DISSOLVED:
        if at < group.invitation_deadline:
            raise InvalidLifecycleTransition(
                "a forming group cannot dissolve before its invitation deadline"
            )
        if accepted_count >= MIN_GROUP_SIZE:
            raise InvalidLifecycleTransition(
                "a group with enough accepted members cannot be dissolved"
            )
    if target in {GroupStatus.ACTIVE, GroupStatus.COMPLETED} and (
        accepted_count < MIN_GROUP_SIZE
    ):
        raise InvalidLifecycleTransition(
            f"an {target} group requires {MIN_CONFIRMED_MEMBERS} accepted members"
        )
    if target == GroupStatus.ACTIVE and at < group.meeting_start:
        raise InvalidLifecycleTransition("a group cannot become active before it starts")
    if target == GroupStatus.COMPLETED and at < group.meeting_end:
        raise InvalidLifecycleTransition("a group cannot complete before it ends")

    return replace(
        group,
        status=target,
        confirmed_at=(
            at
            if target == GroupStatus.CONFIRMED and group.confirmed_at is None
            else group.confirmed_at
        ),
    )


def respond_to_invitation(
    group: GroupLifecycle,
    memberships: Iterable[MembershipLifecycle],
    *,
    student_id: str,
    response: InvitationStatus,
    at: datetime,
) -> LifecycleUpdate:
    """Accept or decline one invitation and confirm the group at three accepts."""
    _require_aware(at, "response timestamp")
    if response not in {InvitationStatus.ACCEPTED, InvitationStatus.DECLINED}:
        raise InvalidLifecycleTransition("an invitation response must accept or decline")

    current_memberships = tuple(memberships)
    member_index = _membership_index(current_memberships, student_id)
    current = current_memberships[member_index]

    if current.invitation_status == response:
        return LifecycleUpdate(group=group, memberships=current_memberships)
    if group.status not in {GroupStatus.FORMING, GroupStatus.CONFIRMED}:
        raise InvalidLifecycleTransition(
            f"invitations cannot change while a group is {group.status}"
        )
    if at >= group.invitation_deadline:
        raise InvalidLifecycleTransition("the invitation deadline has passed")
    if current.invitation_status != InvitationStatus.INVITED:
        raise InvalidLifecycleTransition(
            f"cannot change an {current.invitation_status} invitation to {response}"
        )

    updated_memberships = list(current_memberships)
    updated_memberships[member_index] = replace(current, invitation_status=response)
    accepted_count = accepted_member_count(updated_memberships)
    updated_group = group
    if group.status == GroupStatus.FORMING and accepted_count >= MIN_GROUP_SIZE:
        updated_group = transition_group(
            group,
            GroupStatus.CONFIRMED,
            at=at,
            accepted_count=accepted_count,
        )
    return LifecycleUpdate(
        group=updated_group,
        memberships=tuple(updated_memberships),
    )


def expire_invitations(
    group: GroupLifecycle,
    memberships: Iterable[MembershipLifecycle],
    *,
    at: datetime,
) -> LifecycleUpdate:
    """Expire unanswered invitations and resolve a forming group at its deadline."""
    _require_aware(at, "expiration timestamp")
    current_memberships = tuple(memberships)
    if at < group.invitation_deadline:
        return LifecycleUpdate(group=group, memberships=current_memberships)

    updated_memberships = tuple(
        replace(member, invitation_status=InvitationStatus.EXPIRED)
        if member.invitation_status == InvitationStatus.INVITED
        else member
        for member in current_memberships
    )
    accepted_count = accepted_member_count(updated_memberships)
    updated_group = group
    if group.status == GroupStatus.FORMING:
        target = (
            GroupStatus.CONFIRMED
            if accepted_count >= MIN_GROUP_SIZE
            else GroupStatus.DISSOLVED
        )
        updated_group = transition_group(
            group,
            target,
            at=at,
            accepted_count=accepted_count,
        )
    return LifecycleUpdate(group=updated_group, memberships=updated_memberships)


def advance_group_for_time(
    group: GroupLifecycle,
    *,
    accepted_count: int,
    at: datetime,
) -> GroupLifecycle:
    """Advance a confirmed group through its time-driven states.

    Invitation expiration is intentionally separate so a later worker can update
    group and membership rows in one database transaction.
    """
    _require_aware(at, "lifecycle timestamp")
    updated = group
    if updated.status == GroupStatus.CONFIRMED and at >= updated.meeting_start:
        updated = transition_group(
            updated,
            GroupStatus.ACTIVE,
            at=at,
            accepted_count=accepted_count,
        )
    if updated.status == GroupStatus.ACTIVE and at >= updated.meeting_end:
        updated = transition_group(
            updated,
            GroupStatus.COMPLETED,
            at=at,
            accepted_count=accepted_count,
        )
    return updated


def attendance_status(
    group: GroupLifecycle,
    membership: MembershipLifecycle,
) -> AttendanceStatus:
    """Derive attendance without mixing it into the invitation response."""
    if membership.invitation_status != InvitationStatus.ACCEPTED:
        return AttendanceStatus.NOT_APPLICABLE
    if membership.checked_in_at is not None:
        return AttendanceStatus.CHECKED_IN
    if group.status == GroupStatus.COMPLETED:
        return AttendanceStatus.NO_SHOW
    return AttendanceStatus.PENDING


def check_in_allowed(group: GroupLifecycle, *, at: datetime) -> bool:
    """Whether accepted members may verify attendance at this instant.

    A confirmed group becomes check-in eligible when its actual meeting
    interval starts. ``active`` is also accepted because the first successful
    check-in may already have advanced the durable group state.
    """
    _require_aware(at, "check-in timestamp")
    return (
        group.status in {GroupStatus.CONFIRMED, GroupStatus.ACTIVE}
        and group.meeting_start <= at < group.meeting_end
    )


def accepted_member_count(memberships: Iterable[MembershipLifecycle]) -> int:
    return sum(
        member.invitation_status == InvitationStatus.ACCEPTED
        for member in memberships
    )


def active_capacity_count(memberships: Iterable[MembershipLifecycle]) -> int:
    return sum(
        member.invitation_status
        in {InvitationStatus.INVITED, InvitationStatus.ACCEPTED}
        for member in memberships
    )


def _membership_index(
    memberships: tuple[MembershipLifecycle, ...],
    student_id: str,
) -> int:
    matches = [
        index
        for index, member in enumerate(memberships)
        if member.student_id == student_id
    ]
    if len(matches) != 1:
        raise InvalidLifecycleTransition(
            "exactly one membership is required for the responding student"
        )
    return matches[0]


def _require_aware(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
