import os
import unittest
from uuid import uuid4

from app.db import create_supabase_client
from app.presets import blocks_for
from app.repositories.free_blocks import FreeBlockInput, FreeBlockRepository
from app.repositories.students import StudentRepository


@unittest.skipUnless(
    os.getenv("RUN_SUPABASE_INTEGRATION") == "1",
    "Set RUN_SUPABASE_INTEGRATION=1 to exercise the configured Supabase project",
)
class SupabaseIntegrationTests(unittest.TestCase):
    def test_student_and_free_blocks_persist(self) -> None:
        client = create_supabase_client()
        students = StudentRepository(client)
        free_blocks = FreeBlockRepository(client)
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
