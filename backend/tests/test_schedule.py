from __future__ import annotations

import unittest
from io import BytesIO
from types import SimpleNamespace
from datetime import datetime
from unittest.mock import ANY, MagicMock, Mock, patch

from fastapi.testclient import TestClient
from PIL import Image

from app.auth import create_guest_session
from app.db import get_db_client
from app.gemini_schedule import (
    DEFAULT_GEMINI_MODEL,
    GeminiScheduleParser,
    GeminiScheduleError,
    InvalidGeminiOutputError,
    gemini_response_schema,
    get_schedule_parser,
    validate_schedule_image,
)
from app import store
from app.main import app
from app.repositories.base import RepositoryError
from app.repositories.free_blocks import FreeBlockRepository
from app.routers.schedule import get_configured_schedule_parser
from app.schedule import (
    BusyInterval,
    ExtractedSchedule,
    TimedScheduleEvent,
    merge_busy_intervals,
    suggest_free_blocks,
)
from app.schedule_ai import (
    ScheduleAIConfigurationError,
    get_schedule_parser as get_default_schedule_parser,
)
from tests.fakes import FakeQuery, FakeSupabase


def png_bytes(width: int = 640, height: int = 480) -> bytes:
    output = BytesIO()
    Image.new("RGB", (width, height), color="white").save(output, format="PNG")
    return output.getvalue()


def image_bytes(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (640, 480), color="white").save(output, format=image_format)
    return output.getvalue()


class FreeBlockCalculationTests(unittest.TestCase):
    def test_merges_overlapping_and_adjacent_busy_intervals(self) -> None:
        merged = merge_busy_intervals(
            [
                BusyInterval(1, "11:00", "12:00"),
                BusyInterval(1, "09:30", "10:30"),
                BusyInterval(1, "10:30", "11:15"),
                BusyInterval(2, "13:00", "14:00"),
            ]
        )

        self.assertEqual(
            merged,
            (
                BusyInterval(1, "09:30", "12:00"),
                BusyInterval(2, "13:00", "14:00"),
            ),
        )

    def test_subtracts_busy_time_and_includes_days_with_no_events(self) -> None:
        blocks = suggest_free_blocks(
            [
                BusyInterval(0, "08:00", "10:00"),
                BusyInterval(0, "12:00", "13:30"),
                BusyInterval(0, "17:00", "20:00"),
            ],
            days=(0, 1),
        )

        self.assertEqual(
            [(item.day, item.start_time, item.end_time) for item in blocks],
            [
                (0, "10:00", "12:00"),
                (0, "13:30", "17:00"),
                (1, "09:00", "18:00"),
            ],
        )

    def test_rejects_invalid_intervals_and_matching_windows(self) -> None:
        with self.assertRaisesRegex(ValueError, "end_time must be after"):
            BusyInterval(0, "11:00", "10:00")
        with self.assertRaisesRegex(ValueError, "matching window end"):
            suggest_free_blocks([], window_start="18:00", window_end="09:00")


class GeminiBoundaryTests(unittest.TestCase):
    def test_default_schedule_parser_is_gemini(self) -> None:
        parser = object()
        with patch(
            "app.gemini_schedule.get_gemini_schedule_parser",
            return_value=parser,
        ) as factory:
            self.assertIs(get_default_schedule_parser(), parser)

        factory.assert_called_once_with()

    def test_accepts_supported_image_formats_by_actual_content(self) -> None:
        for image_format, mime_type in (
            ("PNG", "image/png"),
            ("JPEG", "image/jpeg"),
            ("WEBP", "image/webp"),
        ):
            with self.subTest(image_format=image_format):
                content = image_bytes(image_format)
                self.assertEqual(validate_schedule_image(content, mime_type), mime_type)

    def test_parser_uses_inline_bytes_and_structured_output(self) -> None:
        extraction = ExtractedSchedule(
            timed_events=[
                TimedScheduleEvent(
                    weekday="tue",
                    start_time="13:00",
                    end_time="14:00",
                    title="Visible class",
                    event_type="class",
                )
            ]
        )
        generated = SimpleNamespace(parsed=extraction, text=None)
        client_context = MagicMock()
        client = client_context.return_value.__enter__.return_value
        client.models.generate_content.return_value = generated

        with patch("app.gemini_schedule.genai.Client", client_context):
            result = GeminiScheduleParser("secret-key", "test-model").parse(
                b"image bytes",
                "image/png",
            )

        self.assertEqual(result, extraction)
        client_context.assert_called_once_with(
            enterprise=True,
            api_key="secret-key",
            http_options=ANY,
        )
        client_options = client_context.call_args.kwargs["http_options"]
        self.assertEqual(client_options.api_version, "v1")
        call = client.models.generate_content.call_args
        self.assertEqual(call.kwargs["model"], "test-model")
        self.assertEqual(call.kwargs["config"].response_mime_type, "application/json")
        self.assertIsNotNone(call.kwargs["config"].response_schema)
        self.assertIsNone(call.kwargs["config"].response_json_schema)
        self.assertIsNone(call.kwargs["config"].temperature)
        inline_part = call.kwargs["contents"][1]
        self.assertEqual(inline_part.inline_data.data, b"image bytes")
        self.assertEqual(inline_part.inline_data.mime_type, "image/png")

    def test_wire_schema_uses_only_supported_enterprise_fields(self) -> None:
        schema = gemini_response_schema()

        def keys(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    yield key
                    yield from keys(nested)
            elif isinstance(value, list):
                for nested in value:
                    yield from keys(nested)

        schema_keys = set(keys(schema))
        for unsupported in (
            "$defs",
            "$ref",
            "additionalProperties",
            "default",
            "maxLength",
            "minLength",
            "pattern",
        ):
            self.assertNotIn(unsupported, schema_keys)
        # The application model remains strict after Gemini returns JSON.
        with self.assertRaises(ValueError):
            ExtractedSchedule.model_validate({"unexpected": True})

    def test_gemini_model_uses_documented_name_and_default(self) -> None:
        with (
            patch("app.gemini_schedule.load_dotenv"),
            patch.dict(
                "os.environ",
                {
                    "GOOGLE_CLOUD_GEMINI_API_KEY": "test-key",
                    "GEMINI_MODEL": "configured-model",
                },
                clear=True,
            ),
        ):
            configured = get_schedule_parser()

        self.assertEqual(configured.model, "configured-model")

        with (
            patch("app.gemini_schedule.load_dotenv"),
            patch.dict(
                "os.environ",
                {"GOOGLE_CLOUD_GEMINI_API_KEY": "test-key"},
                clear=True,
            ),
        ):
            defaulted = get_schedule_parser()

        self.assertEqual(defaulted.model, DEFAULT_GEMINI_MODEL)

    def test_missing_google_cloud_key_is_rejected(self) -> None:
        with (
            patch("app.gemini_schedule.load_dotenv"),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaises(ScheduleAIConfigurationError),
        ):
            get_schedule_parser()


class ScheduleApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            "os.environ",
            {
                "GUEST_SESSION_SECRET": "test-only-secret-that-is-at-least-32-bytes",
                "CURRENT_TERM": "2026W1",
            },
            clear=True,
        )
        self.environment.start()
        self.database = FakeSupabase()
        self.parser = Mock()
        self._give_the_caller_a_profile("s_current")
        app.dependency_overrides[get_db_client] = lambda: self.database
        app.dependency_overrides[get_configured_schedule_parser] = lambda: self.parser
        self.client = TestClient(app)
        token = create_guest_session("s_current")
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        store.reset()
        self.environment.stop()

    def _give_the_caller_a_profile(self, student_id: str) -> None:
        """Both halves of the split identity, the way signup writes them.

        Identity still lives in two places: app/store.py holds the
        authenticated profile and Supabase holds the matchable row
        (docs/HANDOFF.md section 3). A guest token only verifies while a store
        row with that id exists, and /me/schedule goes through
        onboarded_user(), so seeding Supabase alone gets 401 from every route
        here. POST /students writes both, so this is the real signup path
        rather than a test-only shortcut.
        """
        store.reset()
        store.put(
            store.Student(
                id=student_id,
                first_name="Current",
                auth_sub=f"guest:{student_id}",
                is_guest=True,
            )
        )

    def test_parse_requires_authentication_before_processing_image(self) -> None:
        response = self.client.post(
            "/schedule/parse",
            files={"image": ("calendar.png", png_bytes(), "image/png")},
        )

        self.assertEqual(response.status_code, 401)
        self.parser.parse.assert_not_called()

    def test_parse_returns_validated_events_and_unconfirmed_suggestions(self) -> None:
        self.parser.parse.return_value = ExtractedSchedule(
            timed_events=[
                TimedScheduleEvent(
                    weekday="mon",
                    date="2026-11-02",
                    start_time="10:00",
                    end_time="11:00",
                    title="STAT 406",
                    course_code="STAT 406",
                    event_type="class",
                ),
                TimedScheduleEvent(
                    weekday="mon",
                    date="2026-11-02",
                    start_time="10:30",
                    end_time="12:00",
                    title="Tutorial",
                    event_type="tutorial",
                ),
            ],
            warnings=["One title is partially obscured."],
        )

        response = self.client.post(
            "/schedule/parse",
            headers=self.headers,
            files={"image": ("calendar.png", png_bytes(), "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["timed_events"]), 2)
        self.assertEqual(body["availability_status"], "suggested_not_confirmed")
        self.assertEqual(body["matching_window"]["timezone"], "America/Vancouver")
        self.assertEqual(
            body["suggested_free_blocks"][:2],
            [
                {"day": 0, "start_time": "09:00", "end_time": "10:00"},
                {"day": 0, "start_time": "12:00", "end_time": "18:00"},
            ],
        )
        self.parser.parse.assert_called_once()
        self.assertEqual(self.parser.parse.call_args.args[1], "image/png")

    def test_parse_rejects_malformed_or_mislabeled_uploads(self) -> None:
        malformed = self.client.post(
            "/schedule/parse",
            headers=self.headers,
            files={"image": ("calendar.png", b"not an image", "image/png")},
        )
        mislabeled = self.client.post(
            "/schedule/parse",
            headers=self.headers,
            files={"image": ("calendar.jpg", png_bytes(), "image/jpeg")},
        )

        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(mislabeled.status_code, 422)
        self.parser.parse.assert_not_called()

    def test_parse_sanitizes_invalid_output_and_rate_limits(self) -> None:
        self.parser.parse.side_effect = InvalidGeminiOutputError("private details")
        invalid = self.client.post(
            "/schedule/parse",
            headers=self.headers,
            files={"image": ("calendar.png", png_bytes(), "image/png")},
        )
        self.parser.parse.side_effect = GeminiScheduleError(
            "provider response body",
            rate_limited=True,
        )
        limited = self.client.post(
            "/schedule/parse",
            headers=self.headers,
            files={"image": ("calendar.png", png_bytes(), "image/png")},
        )

        self.assertEqual(invalid.status_code, 502)
        self.assertNotIn("private", invalid.text)
        self.assertEqual(limited.status_code, 429)
        self.assertNotIn("provider response", limited.text)

    def test_confirm_schedule_replaces_only_authenticated_students_blocks(self) -> None:
        memberships_before = [dict(row) for row in self.database.tables["group_members"]]
        self.database.tables["free_blocks"].append(
            {
                "id": 2,
                "student_id": "s_other",
                "day": 4,
                "start_time": "10:00",
                "end_time": "11:00",
            }
        )
        with patch("app.routers.schedule.run_matching") as matching:
            response = self.client.put(
                "/me/schedule",
                headers=self.headers,
                json={
                    "free_blocks": [
                        {"day": 3, "start_time": "14:00", "end_time": "16:00"},
                        {"day": 1, "start_time": "09:00", "end_time": "10:00"},
                    ]
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "saved")
        own = [
            row
            for row in self.database.tables["free_blocks"]
            if row["student_id"] == "s_current"
        ]
        other = [
            row
            for row in self.database.tables["free_blocks"]
            if row["student_id"] == "s_other"
        ]
        self.assertEqual(
            [(row["day"], row["start_time"], row["end_time"]) for row in own],
            [(1, "09:00", "10:00"), (3, "14:00", "16:00")],
        )
        self.assertEqual(len(other), 1)
        self.assertEqual(
            [
                (day, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"))
                for day, start, end in store.get("s_current").free_blocks
            ],
            [(1, "09:00", "10:00"), (3, "14:00", "16:00")],
        )
        self.assertEqual(self.database.tables["group_members"], memberships_before)
        self.assertEqual(matching.call_count, 2)

    def test_saved_schedule_changes_the_gap_returned_by_now(self) -> None:
        day = (datetime.now().weekday() + 1) % 7
        self.database.tables["groups"] = []
        self.database.tables["group_members"] = []
        with patch("app.routers.schedule.run_matching"):
            saved = self.client.put(
                "/me/schedule",
                headers=self.headers,
                json={
                    "free_blocks": [
                        {"day": day, "start_time": "09:15", "end_time": "10:45"}
                    ]
                },
            )

        current = self.client.get("/me/now", headers=self.headers)

        self.assertEqual(saved.status_code, 200)
        self.assertEqual(current.status_code, 200)
        self.assertEqual(
            current.json()["gap"],
            {
                "day": ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[day],
                "start": "09:15",
                "end": "10:45",
            },
        )

    def test_store_failure_is_reported_and_matching_does_not_run(self) -> None:
        with (
            patch("app.routers.schedule.store.update", return_value=None),
            patch("app.routers.schedule.run_matching") as matching,
            self.assertLogs("app.routers.schedule", level="ERROR") as logs,
        ):
            response = self.client.put(
                "/me/schedule",
                headers=self.headers,
                json={
                    "free_blocks": [
                        {"day": 2, "start_time": "11:00", "end_time": "12:30"}
                    ]
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"],
            "The schedule saved incompletely; please try again",
        )
        self.assertIn("supabase_saved=true", logs.output[0])
        self.assertIn("store_present=True", logs.output[0])
        matching.assert_not_called()

    def test_confirm_schedule_rejects_overlap_without_changing_data(self) -> None:
        original = list(self.database.tables["free_blocks"])
        response = self.client.put(
            "/me/schedule",
            headers=self.headers,
            json={
                "free_blocks": [
                    {"day": 1, "start_time": "09:00", "end_time": "11:00"},
                    {"day": 1, "start_time": "10:30", "end_time": "12:00"},
                ]
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.database.tables["free_blocks"], original)

    def test_confirm_schedule_rejects_malformed_and_excessive_blocks(self) -> None:
        malformed = self.client.put(
            "/me/schedule",
            headers=self.headers,
            json={
                "free_blocks": [
                    {"day": 7, "start_time": "9am", "end_time": "10:00"}
                ]
            },
        )
        excessive = self.client.put(
            "/me/schedule",
            headers=self.headers,
            json={
                "free_blocks": [
                    {"day": index % 7, "start_time": "09:00", "end_time": "10:00"}
                    for index in range(36)
                ]
            },
        )

        self.assertEqual(malformed.status_code, 422)
        self.assertEqual(excessive.status_code, 422)

    def test_failed_replacement_restores_old_blocks_and_does_not_match(self) -> None:
        database = FailFirstFreeBlockInsertSupabase()
        original = [
            (row["student_id"], row["day"], row["start_time"][:5], row["end_time"][:5])
            for row in database.tables["free_blocks"]
        ]
        app.dependency_overrides[get_db_client] = lambda: database
        with patch("app.routers.schedule.run_matching") as matching:
            response = self.client.put(
                "/me/schedule",
                headers=self.headers,
                json={
                    "free_blocks": [
                        {"day": 2, "start_time": "12:00", "end_time": "13:00"}
                    ]
                },
            )

        self.assertEqual(response.status_code, 502)
        restored = [
            (row["student_id"], row["day"], row["start_time"][:5], row["end_time"][:5])
            for row in database.tables["free_blocks"]
        ]
        self.assertEqual(restored, original)
        matching.assert_not_called()

    def test_schedule_endpoints_are_documented(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/schedule/parse", paths)
        self.assertIn("/me/schedule", paths)
        self.assertIn("multipart/form-data", paths["/schedule/parse"]["post"]["requestBody"]["content"])


class FailFirstFreeBlockInsertSupabase(FakeSupabase):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_free_block_insert = True

    def table(self, name: str) -> FakeQuery:
        self.tables.setdefault(name, [])
        return FailFirstFreeBlockInsertQuery(self, name)


class FailFirstFreeBlockInsertQuery(FakeQuery):
    def execute(self):
        if (
            self.table_name == "free_blocks"
            and self.action == "insert"
            and self.client.fail_next_free_block_insert
        ):
            self.client.fail_next_free_block_insert = False
            raise RuntimeError("simulated PostgREST insert failure")
        return super().execute()


if __name__ == "__main__":
    unittest.main()
