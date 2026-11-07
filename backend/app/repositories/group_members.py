from typing import Any, Literal

from app.repositories.base import RecordNotFoundError, execute

MemberResponse = Literal["pending", "joined", "skipped"]


class GroupMemberRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_for_student(self, student_id: str) -> list[dict[str, Any]]:
        return execute(
            self.client.table("group_members")
            .select("group_id,student_id,response,arrived_at")
            .eq("student_id", student_id),
            "read student group memberships",
        )

    def list_for_group(self, group_id: str) -> list[dict[str, Any]]:
        return execute(
            self.client.table("group_members")
            .select("group_id,student_id,response,arrived_at")
            .eq("group_id", group_id),
            "read group members",
        )

    def list_for_groups(self, group_ids: list[str]) -> list[dict[str, Any]]:
        if not group_ids:
            return []
        return execute(
            self.client.table("group_members")
            .select("group_id,student_id,response,arrived_at")
            .in_("group_id", group_ids),
            "read memberships for existing groups",
        )

    def create_pending(
        self,
        group_id: str,
        student_ids: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        return execute(
            self.client.table("group_members").insert(
                [
                    {
                        "group_id": group_id,
                        "student_id": student_id,
                        "response": "pending",
                    }
                    for student_id in student_ids
                ]
            ),
            "create pending group memberships",
        )

    def update_response(
        self,
        group_id: str,
        student_id: str,
        response: Literal["joined", "skipped"],
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
