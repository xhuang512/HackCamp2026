from dataclasses import dataclass
from typing import Any

from app.repositories.base import ReferenceDataError, execute


@dataclass(frozen=True)
class FreeBlockInput:
    day: int
    start_time: str
    end_time: str


PRESET_FREE_BLOCKS: dict[str, tuple[FreeBlockInput, ...]] = {
    # The only preset documented by the existing API example. Day follows the
    # supplied SQL schema: Monday=0, Tuesday=1, Thursday=3.
    "tue_thu_afternoon": (
        FreeBlockInput(day=1, start_time="13:00", end_time="15:00"),
        FreeBlockInput(day=3, start_time="13:00", end_time="15:00"),
    )
}


def resolve_preset(preset_schedule: str) -> tuple[FreeBlockInput, ...]:
    try:
        return PRESET_FREE_BLOCKS[preset_schedule]
    except KeyError as exc:
        raise ReferenceDataError(
            f"Unknown preset schedule: {preset_schedule}"
        ) from exc


class FreeBlockRepository:
    def __init__(self, client: Any):
        self.client = client

    def create_for_student(
        self,
        student_id: str,
        blocks: tuple[FreeBlockInput, ...],
    ) -> list[dict[str, Any]]:
        payload = [
            {
                "student_id": student_id,
                "day": block.day,
                "start_time": block.start_time,
                "end_time": block.end_time,
            }
            for block in blocks
        ]
        return execute(
            self.client.table("free_blocks").insert(payload),
            "create student free blocks",
        )

    def list_for_student(self, student_id: str) -> list[dict[str, Any]]:
        return execute(
            self.client.table("free_blocks")
            .select("id,student_id,day,start_time,end_time")
            .eq("student_id", student_id)
            .order("day")
            .order("start_time"),
            "list student free blocks",
        )

    def list_for_students(
        self,
        student_ids: list[str],
        *,
        day: int | None = None,
    ) -> list[dict[str, Any]]:
        if not student_ids:
            return []
        query = (
            self.client.table("free_blocks")
            .select("id,student_id,day,start_time,end_time")
            .in_("student_id", student_ids)
        )
        if day is not None:
            query = query.eq("day", day)
        return execute(
            query.order("day").order("start_time").order("student_id"),
            "list matchable free blocks",
        )
