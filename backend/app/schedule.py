from __future__ import annotations

from dataclasses import dataclass
from datetime import date as CalendarDate
from datetime import time
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
EventType = Literal["class", "tutorial", "lab", "other", "unknown"]

WEEKDAY_TO_NUMBER: dict[Weekday, int] = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}
TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


def parse_wall_time(value: str) -> time:
    """Parse an exact local wall-clock HH:MM value."""
    try:
        parsed = time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("time must use 24-hour HH:MM format") from exc
    if len(value) != 5 or parsed.second or parsed.microsecond:
        raise ValueError("time must use 24-hour HH:MM format")
    return parsed


class TimedScheduleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: Weekday
    date: CalendarDate | None = Field(
        default=None,
        description="Visible calendar date, only when it can be read from the image",
    )
    # google-genai 2.x converts this Pydantic model to its narrower Schema
    # model. That model supports pattern constraints but rejects JSON Schema's
    # `examples` keyword, so examples must remain on the API-only models.
    start_time: str = Field(pattern=TIME_PATTERN)
    end_time: str = Field(pattern=TIME_PATTERN)
    title: str = Field(min_length=1, max_length=160)
    course_code: str | None = Field(default=None, min_length=1, max_length=32)
    event_type: EventType = "unknown"

    @model_validator(mode="after")
    def validate_interval(self) -> TimedScheduleEvent:
        if parse_wall_time(self.start_time) >= parse_wall_time(self.end_time):
            raise ValueError("event end_time must be after start_time")
        if self.date is not None and self.date.weekday() != WEEKDAY_TO_NUMBER[self.weekday]:
            raise ValueError("event date does not match weekday")
        return self


class AllDayScheduleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weekday: Weekday
    date: CalendarDate | None = Field(
        default=None,
        description="Visible calendar date, only when it can be read from the image",
    )
    title: str = Field(min_length=1, max_length=160)
    event_type: EventType = "unknown"

    @model_validator(mode="after")
    def validate_date(self) -> AllDayScheduleEvent:
        if self.date is not None and self.date.weekday() != WEEKDAY_TO_NUMBER[self.weekday]:
            raise ValueError("all-day event date does not match weekday")
        return self


class ExtractedSchedule(BaseModel):
    """Strict shape requested from Gemini schedule extraction."""

    model_config = ConfigDict(extra="forbid")

    timed_events: list[TimedScheduleEvent] = Field(default_factory=list, max_length=100)
    all_day_events: list[AllDayScheduleEvent] = Field(default_factory=list, max_length=50)
    warnings: list[str] = Field(default_factory=list, max_length=50)


@dataclass(frozen=True)
class BusyInterval:
    day: int
    start_time: str
    end_time: str

    def __post_init__(self) -> None:
        if not 0 <= self.day <= 6:
            raise ValueError("day must be between 0 (Monday) and 6 (Sunday)")
        if parse_wall_time(self.start_time) >= parse_wall_time(self.end_time):
            raise ValueError("end_time must be after start_time")


@dataclass(frozen=True)
class SuggestedFreeBlock:
    day: int
    start_time: str
    end_time: str


def merge_busy_intervals(
    intervals: Sequence[BusyInterval],
) -> tuple[BusyInterval, ...]:
    """Sort and merge overlapping or adjacent intervals independently per day."""
    merged: list[BusyInterval] = []
    for interval in sorted(
        intervals,
        key=lambda item: (item.day, item.start_time, item.end_time),
    ):
        if not merged or merged[-1].day != interval.day:
            merged.append(interval)
            continue
        previous = merged[-1]
        if parse_wall_time(interval.start_time) <= parse_wall_time(previous.end_time):
            merged[-1] = BusyInterval(
                day=previous.day,
                start_time=previous.start_time,
                end_time=max(previous.end_time, interval.end_time),
            )
        else:
            merged.append(interval)
    return tuple(merged)


def suggest_free_blocks(
    intervals: Sequence[BusyInterval],
    *,
    window_start: str = "09:00",
    window_end: str = "18:00",
    days: Sequence[int] = (0, 1, 2, 3, 4),
) -> tuple[SuggestedFreeBlock, ...]:
    """Subtract visible busy events from a matching window.

    Results are suggestions derived from a screenshot, not confirmed personal
    availability. Only PUT /me/schedule can persist user-reviewed blocks.
    """
    start = parse_wall_time(window_start)
    end = parse_wall_time(window_end)
    if start >= end:
        raise ValueError("matching window end must be after its start")
    if len(set(days)) != len(days) or any(day < 0 or day > 6 for day in days):
        raise ValueError("matching window days must be unique values from 0 to 6")

    clipped: list[BusyInterval] = []
    selected_days = set(days)
    for interval in intervals:
        if interval.day not in selected_days:
            continue
        interval_start = max(parse_wall_time(interval.start_time), start)
        interval_end = min(parse_wall_time(interval.end_time), end)
        if interval_start < interval_end:
            clipped.append(
                BusyInterval(
                    day=interval.day,
                    start_time=interval_start.strftime("%H:%M"),
                    end_time=interval_end.strftime("%H:%M"),
                )
            )

    by_day: dict[int, list[BusyInterval]] = {day: [] for day in days}
    for interval in merge_busy_intervals(clipped):
        by_day[interval.day].append(interval)

    free: list[SuggestedFreeBlock] = []
    for day in days:
        cursor = window_start
        for busy in by_day[day]:
            if parse_wall_time(cursor) < parse_wall_time(busy.start_time):
                free.append(SuggestedFreeBlock(day, cursor, busy.start_time))
            cursor = max(cursor, busy.end_time)
        if parse_wall_time(cursor) < end:
            free.append(SuggestedFreeBlock(day, cursor, window_end))
    return tuple(free)


def busy_intervals_from_extraction(
    extraction: ExtractedSchedule,
) -> tuple[BusyInterval, ...]:
    return tuple(
        BusyInterval(
            day=WEEKDAY_TO_NUMBER[event.weekday],
            start_time=event.start_time,
            end_time=event.end_time,
        )
        for event in extraction.timed_events
    )
