from typing import Any, Literal

from app.constants import CHECKED_IN, DECLINED, EXPIRED, INVITED, JOINED
from app.repositories.base import (
    CheckInConflictError,
    InvitationConflictError,
    RecordNotFoundError,
    RepositoryError,
    execute,
)

ExternalResponse = Literal["pending", "joined", "skipped"]
InvitationStatus = Literal["invited", "accepted", "declined", "expired"]

_INVITATION_TO_EXTERNAL: dict[str, ExternalResponse] = {
    "invited": "pending",
    "accepted": "joined",
    "declined": "skipped",
    "expired": "skipped",
}
_EXTERNAL_TO_INVITATION: dict[str, InvitationStatus] = {
    "pending": "invited",
    "joined": "accepted",
    "skipped": "declined",
}


def state_of(member: dict[str, Any]) -> str:
    """Return the AGENTS.md member state, including derived check-in state."""
    invitation = str(member.get("invitation_status") or "")
    if not invitation:
        invitation = {
            "pending": INVITED,
            "joined": "accepted",
            "skipped": DECLINED,
        }.get(str(member.get("response") or "pending"), INVITED)
    if invitation == "accepted":
        return CHECKED_IN if member.get("arrived_at") is not None else JOINED
    if invitation == "declined":
        return DECLINED
    if invitation == "expired":
        return EXPIRED
    return INVITED


class GroupMemberRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_for_student(self, student_id: str) -> list[dict[str, Any]]:
        return self._list(
            self.client.table("group_members")
            .select(self._select_columns())
            .eq("student_id", student_id),
            "read student group memberships",
        )

    def list_for_group(self, group_id: str) -> list[dict[str, Any]]:
        return self._list(
            self.client.table("group_members")
            .select(self._select_columns())
            .eq("group_id", group_id),
            "read group members",
        )

    def list_for_groups(self, group_ids: list[str]) -> list[dict[str, Any]]:
        if not group_ids:
            return []
        return self._list(
            self.client.table("group_members")
            .select(self._select_columns())
            .in_("group_id", group_ids),
            "read memberships for existing groups",
        )

    def create_invited(
        self,
        group_id: str,
        student_ids: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        rows = execute(
            self.client.table("group_members").insert(
                [
                    {
                        "group_id": group_id,
                        "student_id": student_id,
                        "invitation_status": "invited",
                    }
                    for student_id in student_ids
                ]
            ),
            "create invited group memberships",
        )
        return [normalize_membership(row) for row in rows]

    def create_joined(self, group_id: str, student_id: str) -> dict[str, Any]:
        """Create an accepted membership for a founder or open-group join."""
        rows = execute(
            self.client.table("group_members").insert(
                {
                    "group_id": group_id,
                    "student_id": student_id,
                    "invitation_status": "accepted",
                }
            ),
            "create accepted group membership",
        )
        if not rows:
            raise RecordNotFoundError("Database did not return the created membership")
        return normalize_membership(rows[0])

    def respond_to_invitation(
        self,
        group_id: str,
        student_id: str,
        response: Literal["joined", "skipped"],
    ) -> dict[str, Any]:
        try:
            rpc_response = self.client.rpc(
                "respond_to_group_invitation",
                {
                    "p_group_id": group_id,
                    "p_student_id": student_id,
                    "p_response": _EXTERNAL_TO_INVITATION[response],
                },
            ).execute()
        except Exception as exc:
            code = _error_attribute(exc, "code")
            message = _error_attribute(exc, "message") or "Invitation response was rejected"
            if code in {"P0002", "22P02"}:
                raise RecordNotFoundError(message) from exc
            if code in {"P0001", "22023"}:
                raise InvitationConflictError(message) from exc
            raise RepositoryError(
                "Database operation failed: respond to group invitation"
            ) from exc

        rows = getattr(rpc_response, "data", None)
        if rows is None:
            raise RepositoryError(
                "Database returned no result: respond to group invitation"
            )
        if not rows:
            raise RecordNotFoundError(
                "No membership exists for the current student and group"
            )
        return normalize_membership(rows[0])

    def check_in_pair(
        self,
        group_id: str,
        scanner_id: str,
        presenter_id: str,
        checked_in_at: str,
    ) -> dict[str, Any]:
        """Atomically check in two accepted members through the database RPC."""
        try:
            rpc_response = self.client.rpc(
                "check_in_group_members",
                {
                    "p_group_id": group_id,
                    "p_scanner_id": scanner_id,
                    "p_presenter_id": presenter_id,
                    "p_checked_in_at": checked_in_at,
                },
            ).execute()
        except Exception as exc:
            code = _error_attribute(exc, "code")
            message = _error_attribute(exc, "message") or "Group check-in was rejected"
            if code in {"P0002", "22P02"}:
                raise RecordNotFoundError(message) from exc
            if code in {"P0001", "22023"}:
                raise CheckInConflictError(message) from exc
            raise RepositoryError("Database operation failed: group check-in") from exc

        rows = getattr(rpc_response, "data", None)
        if rows is None:
            raise RepositoryError("Database returned no result: group check-in")
        if not rows:
            raise RecordNotFoundError("Group check-in returned no membership")
        return dict(rows[0])

    def _list(self, query: Any, operation: str) -> list[dict[str, Any]]:
        return [normalize_membership(row) for row in execute(query, operation)]

    @staticmethod
    def _select_columns() -> str:
        return "group_id,student_id,invitation_status,arrived_at"


def normalize_membership(row: dict[str, Any]) -> dict[str, Any]:
    """Add the legacy wire `response` without changing durable storage names."""
    normalized = dict(row)
    invitation_status = normalized.get("invitation_status")
    response = normalized.get("response")
    if response is None and invitation_status is not None:
        response = _INVITATION_TO_EXTERNAL[str(invitation_status)]
    normalized["invitation_status"] = invitation_status
    normalized["response"] = response
    return normalized


def _error_attribute(error: Exception, name: str) -> str | None:
    value = getattr(error, name, None)
    if value is None and error.args and isinstance(error.args[0], dict):
        value = error.args[0].get(name)
    return str(value) if value is not None else None
