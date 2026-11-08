from __future__ import annotations

import os
import unittest

from dotenv import load_dotenv

from app.gemini_schedule import get_schedule_parser, validate_schedule_image
from app.schedule_ai import ROOT_ENV_FILE
from tests.schedule_reference import EXPECTED_INTERVALS, SCREENSHOT

load_dotenv(ROOT_ENV_FILE, override=False)


@unittest.skipUnless(
    os.getenv("RUN_GEMINI_INTEGRATION") == "1",
    "set RUN_GEMINI_INTEGRATION=1 to call Gemini explicitly",
)
class RealGeminiScheduleIntegrationTests(unittest.TestCase):
    def test_supplied_week_screenshot_has_expected_timed_events(self) -> None:
        if not os.getenv("GOOGLE_CLOUD_GEMINI_API_KEY"):
            self.skipTest("Google Cloud Gemini API key is not configured")
        if not SCREENSHOT.is_file():
            self.skipTest(f"reference screenshot not found at {SCREENSHOT}")

        image = SCREENSHOT.read_bytes()
        mime_type = validate_schedule_image(image, "image/png")
        actual = get_schedule_parser().parse(image, mime_type)

        self.assertEqual(len(actual.timed_events), 13)
        self.assertEqual(
            {
                (event.weekday, event.start_time, event.end_time)
                for event in actual.timed_events
            },
            EXPECTED_INTERVALS,
        )


if __name__ == "__main__":
    unittest.main()
