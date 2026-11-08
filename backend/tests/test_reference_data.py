import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import create_supabase_client, get_db_client
from app.main import app
from app.repositories.reference_data import (
    DEFAULT_LANGUAGES,
    DEFAULT_STUDENT_TAGS,
    ReferenceDataRepository,
    normalize_course_code,
)
from tests.fakes import FakeSupabase


class ReferenceDataTests(unittest.TestCase):
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
        app.dependency_overrides[get_db_client] = lambda: self.database
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.environment.stop()
        create_supabase_client.cache_clear()

    def test_repeated_seed_is_idempotent(self) -> None:
        repository = ReferenceDataRepository(self.database)

        repository.seed_defaults()
        repository.seed_defaults()

        self.assertEqual(len(self.database.tables["languages"]), len(DEFAULT_LANGUAGES))
        self.assertEqual(len(self.database.tables["tags"]), len(DEFAULT_STUDENT_TAGS))
        self.assertEqual(
            len({row["code"] for row in self.database.tables["languages"]}),
            len(DEFAULT_LANGUAGES),
        )
        self.assertEqual(
            len({row["slug"] for row in self.database.tables["tags"]}),
            len(DEFAULT_STUDENT_TAGS),
        )

    def test_options_returns_canonical_ids_and_labels(self) -> None:
        ReferenceDataRepository(self.database).seed_defaults()

        response = self.client.get("/options")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn({"id": "en", "label": "English"}, body["languages"])
        self.assertIn(
            {"id": "transfer", "label": "Transfer student"},
            body["tags"],
        )

    def test_course_normalization_accepts_common_ubc_forms(self) -> None:
        self.assertEqual(normalize_course_code("stat406"), "STAT 406")
        self.assertEqual(normalize_course_code(" cpsc-110 "), "CPSC 110")
        self.assertEqual(normalize_course_code("WRDS 150B"), "WRDS 150B")

    def test_signup_accepts_language_code_name_and_normalized_courses(self) -> None:
        ReferenceDataRepository(self.database).seed_defaults()
        response = self._signup(
            tags=["TRANSFER"],
            languages=["en", "English"],
            courses=["stat406", "STAT 406", "cpsc-110"],
        )

        self.assertEqual(response.status_code, 201)
        student_id = response.json()["student"]["id"]
        language_links = [
            row
            for row in self.database.tables["student_languages"]
            if row["student_id"] == student_id
        ]
        self.assertEqual(
            [row["language_code"] for row in language_links],
            ["en"],
        )
        course_ids = {
            row["course_id"]
            for row in self.database.tables["student_courses"]
            if row["student_id"] == student_id
        }
        courses_by_id = {
            row["id"]: row["code"] for row in self.database.tables["courses"]
        }
        self.assertEqual(
            {courses_by_id[course_id] for course_id in course_ids},
            {"STAT 406", "CPSC 110"},
        )

    def test_existing_and_duplicate_course_codes_are_reused(self) -> None:
        original_course_id = self.database.tables["courses"][0]["id"]

        first = self._signup(courses=["stat302", "STAT 302"])
        second = self._signup(courses=["STAT-302"])

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        matching = [
            row for row in self.database.tables["courses"] if row["code"] == "STAT 302"
        ]
        self.assertEqual(
            matching,
            [
                {
                    "id": original_course_id,
                    "code": "STAT 302",
                    "title": "Introduction",
                }
            ],
        )

    def test_malformed_course_is_rejected_without_creating_student(self) -> None:
        original_count = len(self.database.tables["students"])

        response = self._signup(courses=["statistics 406"])

        self.assertEqual(response.status_code, 422)
        self.assertIn("expected a code such as STAT 406", response.json()["detail"])
        self.assertEqual(len(self.database.tables["students"]), original_count)

    def test_unknown_language_is_rejected(self) -> None:
        response = self._signup(languages=["Klingon"])

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Unknown languages: Klingon")

    def test_unknown_tag_is_rejected(self) -> None:
        response = self._signup(tags=["wizard"])

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Unknown tags: wizard")

    def _signup(
        self,
        *,
        tags: list[str] | None = None,
        languages: list[str] | None = None,
        courses: list[str] | None = None,
    ):
        return self.client.post(
            "/students",
            json={
                "first_name": "Maya",
                "tags": tags or [],
                "languages": languages or [],
                "courses": courses or [],
                "preset_id": "tue-thu-afternoons",
                "guest": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
