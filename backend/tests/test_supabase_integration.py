import os
import unittest
from uuid import uuid4

from app.db import create_supabase_client
from app.repositories.free_blocks import FreeBlockRepository, resolve_preset
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
            free_blocks.create_for_student(
                student_id,
                resolve_preset("tue_thu_afternoon"),
            )
            persisted = free_blocks.list_for_student(student_id)
            self.assertEqual(len(persisted), 2)
            self.assertTrue(all(row["student_id"] == student_id for row in persisted))
        finally:
            students.delete(student_id)
