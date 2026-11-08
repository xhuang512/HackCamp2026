from collections import Counter
from dataclasses import dataclass
from datetime import time
from typing import Any, Iterable, Sequence

from app.constants import MAX_GROUP_SIZE, MIN_GROUP_SIZE


@dataclass(frozen=True)
class GroupPlan:
    """A group whose members share one concrete weekly free interval."""

    day: int
    start_time: time
    end_time: time
    student_ids: tuple[str, ...]


@dataclass(frozen=True)
class _Block:
    student_id: str
    day: int
    start_time: time
    end_time: time


def form_groups(
    free_blocks: Iterable[dict[str, Any]],
    *,
    min_size: int = MIN_GROUP_SIZE,
    max_size: int = MAX_GROUP_SIZE,
) -> list[GroupPlan]:
    """Greedily form deterministic groups with a non-empty common overlap.

    A student is assigned at most once per weekday. The algorithm intentionally
    ignores matching signals; those belong to the later optimizer.
    """
    if min_size < 2 or max_size < min_size:
        raise ValueError("group sizes must satisfy 2 <= min_size <= max_size")

    blocks = [_normalize_block(row) for row in free_blocks]
    plans: list[GroupPlan] = []

    for day in sorted({block.day for block in blocks}):
        available = [block for block in blocks if block.day == day]
        assigned: set[str] = set()

        while True:
            window = _best_overlap_window(available, assigned, min_size)
            if window is None:
                break
            window_start, window_end, covering = window
            group_size = _next_group_size(len(covering), min_size, max_size)
            selected_ids = tuple(sorted(covering)[:group_size])
            selected_blocks = [covering[student_id] for student_id in selected_ids]
            common_start = max(block.start_time for block in selected_blocks)
            common_end = min(block.end_time for block in selected_blocks)

            # The boundary window proves an overlap exists; this is a defensive
            # guard against malformed input or future changes to the selector.
            if common_start >= common_end:
                common_start, common_end = window_start, window_end

            plans.append(
                GroupPlan(
                    day=day,
                    start_time=common_start,
                    end_time=common_end,
                    student_ids=selected_ids,
                )
            )
            assigned.update(selected_ids)

    return plans


def _best_overlap_window(
    blocks: list[_Block],
    assigned: set[str],
    min_size: int,
) -> tuple[time, time, dict[str, _Block]] | None:
    boundaries = sorted(
        {
            boundary
            for block in blocks
            if block.student_id not in assigned
            for boundary in (block.start_time, block.end_time)
        }
    )
    best: tuple[time, time, dict[str, _Block]] | None = None

    for start, end in zip(boundaries, boundaries[1:]):
        if start >= end:
            continue
        covering: dict[str, _Block] = {}
        for block in blocks:
            if (
                block.student_id not in assigned
                and block.start_time <= start
                and block.end_time >= end
            ):
                current = covering.get(block.student_id)
                if current is None or (block.start_time, block.end_time) < (
                    current.start_time,
                    current.end_time,
                ):
                    covering[block.student_id] = block

        if len(covering) < min_size:
            continue
        if best is None or len(covering) > len(best[2]):
            best = (start, end, covering)

    return best


def _next_group_size(available: int, min_size: int, max_size: int) -> int:
    size = min(available, max_size)
    remainder = available - size
    if 0 < remainder < min_size:
        size -= min_size - remainder
    return size


def _normalize_block(row: dict[str, Any]) -> _Block:
    day = int(row["day"])
    start = _parse_time(row["start_time"])
    end = _parse_time(row["end_time"])
    if not 0 <= day <= 6:
        raise ValueError(f"invalid weekday: {day}")
    if start >= end:
        raise ValueError("free block end_time must be after start_time")
    return _Block(
        student_id=str(row["student_id"]),
        day=day,
        start_time=start,
        end_time=end,
    )


def _parse_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    return time.fromisoformat(str(value))


def pick_spot(
    buildings: Sequence[dict[str, Any]],
    favourites: Sequence[Sequence[int]] = (),
    *,
    spread: int = 0,
) -> int:
    """Which building a group meets at.

    AGENTS.md: picked from members' favourite spots, then shortest total
    walk. The first half is real here. The second is not, because there is no
    distance table yet, so the tie-break is `spread`, which the caller varies
    per group.

    That matters more than it sounds. Every group landing on one building
    would put a single pin on the map and one number on the projector, which
    is not a bug in the map but it is a demo with nothing in it.
    """
    if not buildings:
        raise ValueError("pick_spot needs at least one building")

    counts = Counter(
        building_id
        for student_spots in favourites
        for building_id in set(student_spots)
    )
    known = {int(building["id"]) for building in buildings}
    wanted = [
        (count, -building_id)
        for building_id, count in counts.items()
        if building_id in known
    ]
    if wanted:
        return -max(wanted)[1]

    ordered = sorted(int(building["id"]) for building in buildings)
    return ordered[spread % len(ordered)]
