"""Persist time-driven lifecycle changes before group state is read."""

import logging
import time
from datetime import date, datetime, time as wall_time, timezone
from threading import Lock
from typing import Annotated, Callable

from fastapi import Depends
from supabase import Client

from app.db import get_db_client
from app.lifecycle import (
    GroupLifecycle,
    GroupStatus,
    InvitationStatus,
    MembershipLifecycle,
    advance_group_for_time,
    expire_invitations,
)
from app.repositories.group_members import GroupMemberRepository
from app.repositories.groups import GroupRepository
from app.timezones import APPLICATION_TIMEZONE

logger = logging.getLogger(__name__)
REFRESH_INTERVAL_SECONDS = 15.0


class LifecycleRefresher:
    """Throttle lifecycle refreshes per process and keep reads resilient."""

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._monotonic = monotonic
        self._now = now
        self._last_run: float | None = None
        self._lock = Lock()

    def refresh(self, client: Client) -> None:
        tick = self._monotonic()
        with self._lock:
            if (
                self._last_run is not None
                and tick - self._last_run < REFRESH_INTERVAL_SECONDS
            ):
                return
            self._last_run = tick

        try:
            refresh_lifecycle_rows(client, at=self._now())
        except Exception:
            logger.exception("Could not refresh group lifecycle; serving stored state")


refresher = LifecycleRefresher()


def refresh_lifecycle(
    client: Annotated[Client, Depends(get_db_client)],
) -> None:
    """FastAPI dependency shared by every endpoint that reads group state."""
    refresher.refresh(client)


def refresh_lifecycle_rows(client: Client, *, at: datetime) -> None:
    """Apply and persist lifecycle transitions for relevant groups."""
    groups = GroupRepository(client)
    members = GroupMemberRepository(client)
    rows = groups.list_lifecycle_candidates()
    memberships = members.list_for_groups([str(row["id"]) for row in rows])

    by_group: dict[str, list[dict]] = {}
    for membership in memberships:
        by_group.setdefault(str(membership["group_id"]), []).append(membership)

    for row in rows:
        group_id = str(row["id"])
        stored_status = str(row["status"])
        lifecycle_group = _group_lifecycle(row)
        lifecycle_members = tuple(
            _membership_lifecycle(member)
            for member in by_group.get(group_id, [])
        )

        expired = expire_invitations(lifecycle_group, lifecycle_members, at=at)
        expired_ids = tuple(
            after.student_id
            for before, after in zip(lifecycle_members, expired.memberships)
            if before.invitation_status == InvitationStatus.INVITED
            and after.invitation_status == InvitationStatus.EXPIRED
        )
        members.expire_invited(group_id, expired_ids)

        current = expired.group
        if current.status.value != stored_status:
            groups.set_status(
                group_id,
                current.status.value,
                current_status=stored_status,
                at=at,
            )
            stored_status = current.status.value

        advanced = advance_group_for_time(
            current,
            accepted_count=expired.accepted_count,
            at=at,
        )
        if current.status == GroupStatus.CONFIRMED and advanced.status == GroupStatus.COMPLETED:
            groups.set_status(
                group_id,
                GroupStatus.ACTIVE.value,
                current_status=stored_status,
                at=at,
            )
            stored_status = GroupStatus.ACTIVE.value
        if advanced.status.value != stored_status:
            groups.set_status(
                group_id,
                advanced.status.value,
                current_status=stored_status,
                at=at,
            )


def _group_lifecycle(row: dict) -> GroupLifecycle:
    on_date = date.fromisoformat(str(row["on_date"]))
    start = wall_time.fromisoformat(str(row["start_time"]))
    end = wall_time.fromisoformat(str(row["end_time"]))
    return GroupLifecycle(
        status=GroupStatus(str(row["status"])),
        invitation_deadline=_timestamp(row["invite_expires_at"]),
        meeting_start=datetime.combine(on_date, start, tzinfo=APPLICATION_TIMEZONE),
        meeting_end=datetime.combine(on_date, end, tzinfo=APPLICATION_TIMEZONE),
        confirmed_at=(
            _timestamp(row["confirmed_at"])
            if row.get("confirmed_at") is not None
            else None
        ),
    )


def _membership_lifecycle(row: dict) -> MembershipLifecycle:
    return MembershipLifecycle(
        student_id=str(row["student_id"]),
        invitation_status=InvitationStatus(str(row["invitation_status"])),
        checked_in_at=(
            _timestamp(row["arrived_at"])
            if row.get("arrived_at") is not None
            else None
        ),
    )


def _timestamp(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("lifecycle timestamps must be timezone-aware")
    return parsed
