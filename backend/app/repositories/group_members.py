from datetime import datetime, timezone
from typing import Any, Literal

from app.constants import CHECKED_IN, INVITED, JOINED
from app.repositories.base import RecordNotFoundError, execute

# The states the response column can hold. checked_in is absent on purpose:
# a member who has checked in is still a joined member, so check-in is the
# arrived_at timestamp and state_of() derives the fifth state from it.
MemberResponse = Literal["invited", "joined", "declined", "expired"]

COLUMNS = "group_id,student_id,response,arrived_at"


def state_of(member: dict[str, Any]) -> str:
    """The member state AGENTS.md names, including checked_in.

    One function so the five states are derived identically everywhere. Four
    live in the column; the fifth is a joined member with an arrival time.
    """
    response = str(member.get("response") or INVITED)
    if response == JOINED and member.get("arrived_at") is not None:
        return CHECKED_IN
    return response


class GroupMemberRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_for_student(self, student_id: str) -> list[dict[str, Any]]:
        return execute(
            self.client.table("group_members")
            .select(COLUMNS)
            .eq("student_id", student_id),
            "read student group memberships",
        )

    def list_for_group(self, group_id: str) -> list[dict[str, Any]]:
        return execute(
            self.client.table("group_members").select(COLUMNS).eq("group_id", group_id),
            "read group members",
        )

    def list_for_groups(self, group_ids: list[str]) -> list[dict[str, Any]]:
        if not group_ids:
            return []
        return execute(
            self.client.table("group_members")
            .select(COLUMNS)
            .in_("group_id", group_ids),
            "read memberships for existing groups",
        )

    def create_pending(
        self,
        group_id: str,
        student_ids: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        """Invite students to a group.

        The name is the one the matcher already calls, kept so nothing
        upstream changes. The state it writes is `invited`, which is what
        AGENTS.md calls the state the old `pending` meant.
        """
        return execute(
            self.client.table("group_members").insert(
                [
                    {
                        "group_id": group_id,
                        "student_id": student_id,
                        "response": INVITED,
                    }
                    for student_id in student_ids
                ]
            ),
            "create pending group memberships",
        )

    def create_joined(self, group_id: str, student_id: str) -> dict[str, Any]:
        """The student who starts a group is in it, not invited to it."""
        rows = execute(
            self.client.table("group_members").insert(
                {
                    "group_id": group_id,
                    "student_id": student_id,
                    "response": JOINED,
                }
            ),
            "create group founder membership",
        )
        if not rows:
            raise RecordNotFoundError("Database did not return the created membership")
        return rows[0]

    def update_response(
        self,
        group_id: str,
        student_id: str,
        response: MemberResponse,
    ) -> dict[str, Any]:
        rows = execute(
            self.client.table("group_members")
            .update({"response": response})
            .eq("group_id", group_id)
            .eq("student_id", student_id),
            "update group membership response",
        )
        if not rows:
            raise RecordNotFoundError(
                "No membership exists for the current student and group"
            )
        return rows[0]

    def mark_arrived(self, group_id: str, student_ids: tuple[str, ...]) -> int:
        """Check these members in. Returns how many rows actually changed.

        Only members who have joined and have no arrival time yet are
        touched, which is what makes repeat scans of the same pair change
        nothing, exactly as AGENTS.md requires.
        """
        members = {
            str(member["student_id"]): member for member in self.list_for_group(group_id)
        }
        now = datetime.now(timezone.utc).isoformat()
        changed = 0
        for student_id in student_ids:
            member = members.get(student_id)
            if member is None or member.get("response") != JOINED:
                continue
            if member.get("arrived_at") is not None:
                continue
            execute(
                self.client.table("group_members")
                .update({"arrived_at": now})
                .eq("group_id", group_id)
                .eq("student_id", student_id),
                "record group check-in",
            )
            changed += 1
        return changed
