from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.schedule import ExtractedSchedule
from app.schedule_ai import (
    ROOT_ENV_FILE,
    SCHEDULE_EXTRACTION_PROMPT,
    MAX_IMAGE_BYTES,
    InvalidScheduleImageError,
    InvalidScheduleOutputError,
    ScheduleAIConfigurationError,
    ScheduleAIError,
    validate_schedule_image,
)

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
logger = logging.getLogger(__name__)

GeminiConfigurationError = ScheduleAIConfigurationError


class GeminiScheduleError(ScheduleAIError):
    pass


class InvalidGeminiOutputError(InvalidScheduleOutputError, GeminiScheduleError):
    pass


def gemini_response_schema() -> dict[str, Any]:
    """Return the supported Agent Platform structured-output subset.

    Pydantic's full JSON Schema includes references and validation constraints
    that the Google Cloud GenerateContent structured-output endpoint rejects.
    The provider receives only the fields needed to shape its JSON. The full
    ``ExtractedSchedule`` model remains the authority for local validation.
    """
    weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    event_types = ["class", "tutorial", "lab", "other", "unknown"]
    common_properties = {
        "weekday": {"type": "STRING", "enum": weekdays},
        "date": {
            "type": "STRING",
            "nullable": True,
            "description": "Visible YYYY-MM-DD date, or null when not visible",
        },
        "title": {"type": "STRING"},
        "event_type": {"type": "STRING", "enum": event_types},
    }
    timed_event = {
        "type": "OBJECT",
        "properties": {
            **common_properties,
            "start_time": {
                "type": "STRING",
                "description": "Visible local start time in 24-hour HH:MM format",
            },
            "end_time": {
                "type": "STRING",
                "description": "Visible local end time in 24-hour HH:MM format",
            },
            "course_code": {
                "type": "STRING",
                "nullable": True,
                "description": "Visible course code, or null when not supported",
            },
        },
        "required": ["weekday", "start_time", "end_time", "title"],
    }
    all_day_event = {
        "type": "OBJECT",
        "properties": common_properties,
        "required": ["weekday", "title"],
    }
    return {
        "type": "OBJECT",
        "properties": {
            "timed_events": {"type": "ARRAY", "items": timed_event},
            "all_day_events": {"type": "ARRAY", "items": all_day_event},
            "warnings": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["timed_events", "all_day_events", "warnings"],
    }


class GeminiScheduleParser:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def parse(self, image_bytes: bytes, mime_type: str) -> ExtractedSchedule:
        try:
            with genai.Client(
                enterprise=True,
                api_key=self.api_key,
                http_options=types.HttpOptions(api_version="v1"),
            ) as client:
                response = client.models.generate_content(
                    model=self.model,
                    contents=[
                        SCHEDULE_EXTRACTION_PROMPT,
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=gemini_response_schema(),
                    ),
                )
        except errors.APIError as exc:
            logger.warning(
                "Google Cloud Gemini request failed (code=%s, status=%s)",
                getattr(exc, "code", None),
                getattr(exc, "status", None),
            )
            raise GeminiScheduleError(
                "Google Cloud Gemini schedule extraction failed",
                rate_limited=getattr(exc, "code", None) == 429,
                authentication_failed=getattr(exc, "code", None) in (401, 403),
            ) from exc
        except ValidationError as exc:
            locations = [
                ".".join(str(part) for part in error.get("loc", ()))
                for error in exc.errors(include_url=False, include_input=False)
            ]
            logger.error(
                "Google Cloud Gemini SDK schema validation failed at: %s",
                ", ".join(locations) or "unknown location",
            )
            raise InvalidGeminiOutputError(
                "Gemini SDK rejected the structured response schema"
            ) from exc
        except Exception as exc:
            logger.error(
                "Google Cloud Gemini SDK request failed (%s)",
                type(exc).__name__,
            )
            raise GeminiScheduleError("Gemini schedule extraction failed") from exc

        try:
            if isinstance(response.parsed, ExtractedSchedule):
                return response.parsed
            if response.parsed is not None:
                return ExtractedSchedule.model_validate(response.parsed)
            if response.text:
                return ExtractedSchedule.model_validate_json(response.text)
        except (ValidationError, ValueError, TypeError) as exc:
            raise InvalidGeminiOutputError(
                "Gemini returned invalid schedule data"
            ) from exc
        raise InvalidGeminiOutputError("Gemini returned no schedule data")


def get_gemini_schedule_parser() -> GeminiScheduleParser:
    load_dotenv(ROOT_ENV_FILE, override=False)
    api_key = os.getenv("GOOGLE_CLOUD_GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigurationError(
            "Google Cloud Gemini schedule parsing is not configured"
        )
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    model = model.strip()
    if not model:
        raise GeminiConfigurationError("Gemini schedule model is not configured")
    return GeminiScheduleParser(api_key, model)


# Compatibility alias for existing callers that import the provider-specific
# factory directly. New code should use app.schedule_ai.get_schedule_parser.
get_schedule_parser = get_gemini_schedule_parser
