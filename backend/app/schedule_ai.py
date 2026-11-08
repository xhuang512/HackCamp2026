from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Protocol

from PIL import Image, UnidentifiedImageError

from app.schedule import ExtractedSchedule

ROOT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

SCHEDULE_EXTRACTION_PROMPT = """
Read only the events visibly present in this calendar screenshot.

Return every visible timed event with its weekday, 24-hour local start and end
time, visible title, optional course code, and best-supported event type. Keep
all-day events in all_day_events, never in timed_events. Use event_type
"unknown" when the image does not support a more specific classification.

Do not invent hidden events, missing times, dates, or recurrence rules. A
one-week view does not prove that an event repeats. Set date only when a full
calendar date is visibly supported. Preserve the displayed local wall-clock
times; the application timezone is America/Vancouver. If text or a boundary is
uncertain, include a concise warning instead of guessing. Do not infer personal
availability: the server calculates only unconfirmed free-time suggestions.
""".strip()


class ScheduleParser(Protocol):
    def parse(self, image_bytes: bytes, mime_type: str) -> ExtractedSchedule: ...


class ScheduleAIConfigurationError(RuntimeError):
    pass


class ScheduleAIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        rate_limited: bool = False,
        authentication_failed: bool = False,
    ):
        super().__init__(message)
        self.rate_limited = rate_limited
        self.authentication_failed = authentication_failed


class InvalidScheduleOutputError(ScheduleAIError):
    pass


def get_schedule_parser() -> ScheduleParser:
    """Build the Google Cloud Gemini schedule extraction client."""
    from app.gemini_schedule import get_gemini_schedule_parser

    return get_gemini_schedule_parser()


SUPPORTED_IMAGE_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_DIMENSION = 12_000
MAX_IMAGE_PIXELS = 50_000_000


class InvalidScheduleImageError(ValueError):
    pass


def validate_schedule_image(
    content: bytes,
    declared_content_type: str | None,
) -> str:
    """Validate actual image bytes and return their canonical MIME type."""
    if declared_content_type not in set(SUPPORTED_IMAGE_TYPES.values()):
        raise InvalidScheduleImageError(
            "Upload must declare PNG, JPEG, or WebP image content"
        )
    if not content:
        raise InvalidScheduleImageError("Uploaded image is empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise InvalidScheduleImageError("Uploaded image exceeds the 10 MB limit")
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise InvalidScheduleImageError("Upload is not a valid image") from exc

    actual_content_type = SUPPORTED_IMAGE_TYPES.get(str(image_format).upper())
    if actual_content_type is None:
        raise InvalidScheduleImageError("Image must be PNG, JPEG, or WebP")
    if actual_content_type != declared_content_type:
        raise InvalidScheduleImageError(
            "Declared content type does not match the uploaded image"
        )
    if (
        width < 1
        or height < 1
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise InvalidScheduleImageError("Image dimensions are outside supported limits")
    return actual_content_type
