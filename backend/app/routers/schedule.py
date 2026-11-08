from __future__ import annotations

import logging
import os
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from supabase import Client

from app import store
from app.auth import get_current_student_id
from app.db import get_db_client
from app.schedule_ai import (
    MAX_IMAGE_BYTES,
    InvalidScheduleOutputError,
    ScheduleAIConfigurationError,
    ScheduleAIError,
    ScheduleParser,
    InvalidScheduleImageError,
    get_schedule_parser,
    validate_schedule_image,
)
from app.matching import next_matching_dates, run_matching
from app.repositories import RepositoryError
from app.repositories.free_blocks import FreeBlockInput, FreeBlockRepository
from app.schedule import (
    TIME_PATTERN,
    AllDayScheduleEvent,
    TimedScheduleEvent,
    busy_intervals_from_extraction,
    parse_wall_time,
    suggest_free_blocks,
)

router = APIRouter(tags=["schedule"])
logger = logging.getLogger(__name__)
MAX_CONFIRMED_FREE_BLOCKS = 35


class FreeBlockModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int = Field(ge=0, le=6, description="Monday=0 through Sunday=6")
    start_time: str = Field(pattern=TIME_PATTERN, examples=["13:00"])
    end_time: str = Field(pattern=TIME_PATTERN, examples=["15:00"])

    @model_validator(mode="after")
    def validate_interval(self) -> FreeBlockModel:
        if parse_wall_time(self.start_time) >= parse_wall_time(self.end_time):
            raise ValueError("end_time must be after start_time")
        return self


class MatchingWindow(BaseModel):
    timezone: Literal["America/Vancouver"] = "America/Vancouver"
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    start_time: str = Field(default="09:00", pattern=TIME_PATTERN)
    end_time: str = Field(default="18:00", pattern=TIME_PATTERN)

    @model_validator(mode="after")
    def validate_window(self) -> MatchingWindow:
        if not self.days or len(set(self.days)) != len(self.days):
            raise ValueError("matching window days must be non-empty and unique")
        if any(day < 0 or day > 6 for day in self.days):
            raise ValueError("matching window days must be between 0 and 6")
        if parse_wall_time(self.start_time) >= parse_wall_time(self.end_time):
            raise ValueError("matching window end must be after its start")
        return self


class ScheduleParseResponse(BaseModel):
    timed_events: list[TimedScheduleEvent]
    all_day_events: list[AllDayScheduleEvent]
    warnings: list[str]
    suggested_free_blocks: list[FreeBlockModel]
    matching_window: MatchingWindow
    availability_status: Literal["suggested_not_confirmed"] = (
        "suggested_not_confirmed"
    )


class ScheduleUpdateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "free_blocks": [
                    {"day": 1, "start_time": "13:00", "end_time": "15:00"}
                ]
            }
        },
    )

    free_blocks: list[FreeBlockModel] = Field(
        max_length=MAX_CONFIRMED_FREE_BLOCKS,
        description="User-reviewed availability; at most 35 blocks",
    )

    @model_validator(mode="after")
    def reject_overlaps(self) -> ScheduleUpdateRequest:
        ordered = sorted(
            self.free_blocks,
            key=lambda block: (block.day, block.start_time, block.end_time),
        )
        for previous, current in zip(ordered, ordered[1:]):
            if (
                previous.day == current.day
                and parse_wall_time(current.start_time)
                < parse_wall_time(previous.end_time)
            ):
                raise ValueError("free blocks must not overlap")
        return self


class ScheduleUpdateResponse(BaseModel):
    status: Literal["saved"] = "saved"
    free_blocks: list[FreeBlockModel]


def get_configured_schedule_parser() -> ScheduleParser:
    try:
        return get_schedule_parser()
    except ScheduleAIConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schedule parsing is not configured",
        ) from exc


def get_configured_matching_window() -> MatchingWindow:
    try:
        days = [
            int(value.strip())
            for value in os.getenv("SCHEDULE_MATCHING_DAYS", "0,1,2,3,4").split(",")
            if value.strip()
        ]
        return MatchingWindow(
            days=days,
            start_time=os.getenv("SCHEDULE_MATCHING_WINDOW_START", "09:00"),
            end_time=os.getenv("SCHEDULE_MATCHING_WINDOW_END", "18:00"),
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Schedule matching window is not configured correctly",
        ) from exc


@router.post(
    "/schedule/parse",
    response_model=ScheduleParseResponse,
    summary="Parse a calendar screenshot",
    description=(
        "Extracts visible events and calculates unconfirmed free-time suggestions. "
        "The screenshot and result are not persisted, and matching is not triggered."
    ),
)
async def parse_schedule(
    student_id: Annotated[str, Depends(get_current_student_id)],
    image: Annotated[
        UploadFile,
        File(description="PNG, JPEG, or WebP calendar screenshot; maximum 10 MB"),
    ],
    parser: Annotated[
        ScheduleParser,
        Depends(get_configured_schedule_parser),
    ],
    matching_window: Annotated[
        MatchingWindow,
        Depends(get_configured_matching_window),
    ],
) -> ScheduleParseResponse:
    # Authentication is intentionally resolved before any image is read. The
    # opaque student id is not sent to an AI provider or written to logs.
    del student_id
    content = await image.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Uploaded image exceeds the 10 MB limit",
        )
    try:
        mime_type = validate_schedule_image(content, image.content_type)
    except InvalidScheduleImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    try:
        extraction = parser.parse(content, mime_type)
    except InvalidScheduleOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Schedule parsing returned an invalid result; please try again",
        ) from exc
    except ScheduleAIError as exc:
        if exc.rate_limited:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Schedule parsing is temporarily rate limited; please try later",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Schedule parsing is temporarily unavailable; please try again",
        ) from exc

    # Section 3 of docs/feature-plans.md asks for two distinguishable parse
    # failures: 503 when parsing is switched off, and 422 when this image is
    # not a timetable. A model that reads no events at all is the second case.
    # It is not a 502, because nothing failed; the picture was wrong. Leaving
    # it a 200 is worse than either, because the editor would then replace a
    # real schedule with an empty one and call that success.
    if not extraction.timed_events and not extraction.all_day_events:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="No timetable events were found in this image",
        )

    suggestions = suggest_free_blocks(
        busy_intervals_from_extraction(extraction),
        window_start=matching_window.start_time,
        window_end=matching_window.end_time,
        days=matching_window.days,
    )
    return ScheduleParseResponse(
        timed_events=extraction.timed_events,
        all_day_events=extraction.all_day_events,
        warnings=extraction.warnings,
        suggested_free_blocks=[
            FreeBlockModel(
                day=block.day,
                start_time=block.start_time,
                end_time=block.end_time,
            )
            for block in suggestions
        ],
        matching_window=matching_window,
    )


@router.put(
    "/me/schedule",
    response_model=ScheduleUpdateResponse,
    summary="Confirm reviewed availability",
    description=(
        "Replaces the authenticated student's reviewed free blocks using a batched "
        "insert with compensating rollback, then attempts existing matching. "
        "Existing group invitations and confirmed groups are not changed."
    ),
)
def update_schedule(
    request: ScheduleUpdateRequest,
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> ScheduleUpdateResponse:
    ordered = sorted(
        request.free_blocks,
        key=lambda block: (block.day, block.start_time, block.end_time),
    )
    blocks = tuple(
        FreeBlockInput(
            day=block.day,
            start_time=block.start_time,
            end_time=block.end_time,
        )
        for block in ordered
    )
    try:
        FreeBlockRepository(client).replace_for_student(student_id, blocks)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not save the reviewed schedule",
        ) from exc

    # Bridge while identity is split between store.py and Supabase. Remove
    # this mirror when HANDOFF.md section 9 moves identity fully into Supabase.
    memory_blocks: list[store.FreeBlock] = [
        (
            block.day,
            parse_wall_time(block.start_time),
            parse_wall_time(block.end_time),
        )
        for block in ordered
    ]
    try:
        updated = store.update(student_id, free_blocks=memory_blocks)
    except Exception as exc:
        current = store.get(student_id)
        logger.exception(
            "Schedule stores diverged for %s: supabase_saved=true "
            "supabase_block_count=%d store_present=%s store_block_count=%d",
            student_id,
            len(blocks),
            current is not None,
            0 if current is None else len(current.free_blocks),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The schedule saved incompletely; please try again",
        ) from exc
    if updated is None:
        current = store.get(student_id)
        logger.error(
            "Schedule stores diverged for %s: supabase_saved=true "
            "supabase_block_count=%d store_present=%s store_block_count=%d",
            student_id,
            len(blocks),
            current is not None,
            0 if current is None else len(current.free_blocks),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The schedule saved incompletely; please try again",
        )

    for target_date in next_matching_dates({block.day for block in blocks}):
        try:
            run_matching(client, target_date, persist=True)
        except RepositoryError:
            # The schedule save is complete. Registration follows the same
            # best-effort behavior and the development CLI can retry matching.
            logger.exception(
                "Automatic matching failed after schedule update for %s on %s",
                student_id,
                target_date,
            )

    return ScheduleUpdateResponse(
        free_blocks=[FreeBlockModel.model_validate(block) for block in ordered]
    )
