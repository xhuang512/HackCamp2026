import os
import unittest
from uuid import uuid4

from dotenv import load_dotenv

from app.db import ROOT_ENV_FILE, create_supabase_client
from app.presets import blocks_for
from app.repositories.free_blocks import FreeBlockInput, FreeBlockRepository
from app.repositories.students import StudentRepository


load_dotenv(ROOT_ENV_FILE, override=False)


@unittest.skipUnless(
    os.getenv("RUN_SUPABASE_INTEGRATION") == "1",
    "Set RUN_SUPABASE_INTEGRATION=1 to exercise the configured Supabase project",
)
class SupabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if (
            os.getenv("SUPABASE_TEST_CONFIRM_WRITES")
            != "YES_I_AM_USING_A_SAFE_TEST_DATABASE"
        ):
            raise RuntimeError("Safe test-database write confirmation is missing")

        create_supabase_client.cache_clear()
        cls.client = create_supabase_client()

    @classmethod
    def tearDownClass(cls) -> None:
        create_supabase_client.cache_clear()

    def test_student_and_free_blocks_persist(self) -> None:
        students = StudentRepository(self.client)
        free_blocks = FreeBlockRepository(self.client)
        created = students.create(f"Integration-{uuid4().hex[:8]}")
        student_id = str(created["id"])

        try:
            # app/presets.py is now the only preset list. The repository's
            # own copy had one underscored id that matched no real preset.
            free_blocks.create_for_student(
                student_id,
                tuple(
                    FreeBlockInput(
                        day=day,
                        start_time=start.strftime("%H:%M"),
                        end_time=end.strftime("%H:%M"),
                    )
                    for day, start, end in blocks_for("tue-thu-afternoons")
                ),
            )
            persisted = free_blocks.list_for_student(student_id)
            self.assertEqual(len(persisted), 2)
            self.assertTrue(all(row["student_id"] == student_id for row in persisted))
        finally:
            students.delete(student_id)
