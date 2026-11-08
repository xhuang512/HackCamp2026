"""The preset schedules onboarding offers, and what each one means in hours.

The ids are a contract with two other places:

  * frontend/src/lib/presets.js shows these ids and sends one back in
    POST /students. Its labels are what a student reads; only the ids have to
    match.
  * seed.py gives its fake students the same ids, so a preset a real student
    picks already has hundreds of people on it and the optimizer has someone
    to match them with.

Add rather than rename. A renamed id silently stops matching every seeded
student who used the old one.

`day` is 0 for Monday, matching free_blocks.day in schema.sql. Blocks are the
gaps between classes, not the classes: free time is the only thing the matcher
reads and the only thing another student is ever shown.
"""

from datetime import time

FreeBlock = tuple[int, time, time]


def _b(day: int, start: str, end: str) -> FreeBlock:
    hh, mm = start.split(":")
    eh, em = end.split(":")
    return day, time(int(hh), int(mm)), time(int(eh), int(em))


PRESETS: dict[str, list[FreeBlock]] = {
    "mwf-midday": [
        _b(0, "12:00", "14:00"),
        _b(2, "12:00", "15:00"),
        _b(4, "12:00", "14:00"),
    ],
    "tue-thu-afternoons": [
        _b(1, "13:00", "15:00"),
        _b(3, "13:00", "15:00"),
    ],
    "tue-thu-mornings": [
        _b(1, "10:00", "12:00"),
        _b(3, "10:00", "12:00"),
    ],
    "long-wednesday": [
        _b(2, "11:00", "15:00"),
    ],
    "commuter-two-days": [
        _b(0, "11:00", "13:00"),
        _b(0, "15:00", "17:00"),
        _b(2, "11:00", "13:00"),
        _b(2, "15:00", "17:00"),
    ],
    "late-starts": [
        _b(0, "10:00", "12:00"),
        _b(1, "10:00", "12:00"),
        _b(3, "10:00", "12:00"),
    ],
    "evening-classes": [
        _b(1, "16:00", "18:00"),
        _b(3, "16:00", "18:00"),
    ],
}


def blocks_for(preset_id: str) -> list[FreeBlock] | None:
    """The free blocks a preset expands into, or None if the id is unknown."""
    return PRESETS.get(preset_id)
