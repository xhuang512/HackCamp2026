from collections import Counter
from typing import Any

from app.repositories.base import RepositoryError, database_error_code, execute
from app.repositories.reference_data import ReferenceDataRepository


class StudentRepository:
    def __init__(self, client: Any):
        self.client = client

    def create(self, first_name: str) -> dict[str, Any]:
        rows = execute(
            self.client.table("students").insert(
                {"first_name": first_name, "is_guest": True}
            ),
            "create student",
        )
        if not rows:
            raise RepositoryError("Database did not return the created student")
        return rows[0]

    def list_matchable(self) -> list[dict[str, Any]]:
        return execute(
            self.client.table("students")
            .select("id")
            .eq("paused", False)
            .is_("deleted_at", "null")
            .order("id"),
            "read matchable students",
        )

    def update_profile(
        self,
        student_id: str,
        *,
        first_name: str | None = None,
        paused: bool | None = None,
        visibility: str | None = None,
    ) -> None:
        """Push identity changes onto the row the matcher reads.

        This is the write that was missing. Identity lives in store.py, in
        memory, while list_matchable() filters the Supabase `paused` column,
        so a student who tapped pause kept being formed into groups. AGENTS.md
        says pause and visibility are always respected by matching, which
        means they have to reach this table and not just the dict.

        Every argument is optional and None means "leave it alone", so a
        caller changing one field cannot blank the others.
        """
        changes = {
            column: value
            for column, value in (
                ("first_name", first_name),
                ("paused", paused),
                ("visibility", visibility),
            )
            if value is not None
        }
        if not changes:
            return
        execute(
            self.client.table("students").update(changes).eq("id", student_id),
            "update student profile",
        )

    def set_spots(self, student_id: str, building_ids: list[int]) -> None:
        """Replace the student's favourite spots, in the order given.

        Replace rather than merge: the Me tab sends the whole list, so a
        removed spot has to actually disappear. AGENTS.md caps it at three and
        the API enforces that before this is called.
        """
        try:
            execute(
                self.client.table("student_spots").delete().eq("student_id", student_id),
                "clear student favourite spots",
            )
        except RepositoryError as exc:
            if database_error_code(exc) == "PGRST205":
                return
            raise
        if not building_ids:
            return
        execute(
            self.client.table("student_spots").insert(
                [
                    {
                        "student_id": student_id,
                        "building_id": building_id,
                        "rank": index + 1,
                    }
                    for index, building_id in enumerate(building_ids)
                ]
            ),
            "create student favourite spots",
        )

    def list_spot_ids(self, student_ids: list[str]) -> dict[str, list[int]]:
        """Favourite building ids per student, best first.

        Takes a list because pick_spot asks about a whole group at once, and
        one query beats five.
        """
        if not student_ids:
            return {}
        try:
            rows = execute(
                self.client.table("student_spots")
                .select("student_id,building_id,rank")
                .in_("student_id", student_ids)
                .order("rank"),
                "read student favourite spots",
            )
        except RepositoryError as exc:
            if database_error_code(exc) == "PGRST205":
                return {}
            raise
        spots: dict[str, list[int]] = {}
        for row in rows:
            spots.setdefault(str(row["student_id"]), []).append(int(row["building_id"]))
        return spots

    def delete(self, student_id: str) -> None:
        execute(
            self.client.table("students").delete().eq("id", student_id),
            "roll back student creation",
        )

    def add_tags(self, student_id: str, slugs: list[str]) -> None:
        if not slugs:
            return
        by_slug = ReferenceDataRepository(self.client).resolve_tags(slugs)
        execute(
            self.client.table("student_tags").insert(
                [
                    {"student_id": student_id, "tag_id": by_slug[slug]}
                    for slug in by_slug
                ]
            ),
            "create student tags",
        )

    def add_languages(self, student_id: str, names: list[str]) -> None:
        if not names:
            return
        codes = ReferenceDataRepository(self.client).resolve_languages(names)
        execute(
            self.client.table("student_languages").insert(
                [
                    {
                        "student_id": student_id,
                        "language_code": code,
                    }
                    for code in codes
                ]
            ),
            "create student languages",
        )

    def add_courses(self, student_id: str, codes: list[str], term: str) -> None:
        if not codes:
            return
        by_code = ReferenceDataRepository(self.client).resolve_or_create_courses(codes)
        execute(
            self.client.table("student_courses").insert(
                [
                    {
                        "student_id": student_id,
                        "course_id": by_code[code],
                        "term": term,
                    }
                    for code in by_code
                ]
            ),
            "create student courses",
        )

    def public_names(self, student_ids: list[str]) -> dict[str, str]:
        if not student_ids:
            return {}
        rows = execute(
            self.client.table("students")
            .select("id,first_name")
            .in_("id", student_ids)
            .is_("deleted_at", "null"),
            "read group member names",
        )
        return {row["id"]: row["first_name"] for row in rows}

    def shared_signals(self, student_ids: list[str]) -> list[str]:
        if len(student_ids) < 2:
            return []

        courses = self._shared_reference_values(
            link_table="student_courses",
            student_ids=student_ids,
            reference_table="courses",
            reference_id="course_id",
            value_column="code",
        )
        tags = self._shared_reference_values(
            link_table="student_tags",
            student_ids=student_ids,
            reference_table="tags",
            reference_id="tag_id",
            value_column="label",
        )
        languages = self._shared_reference_values(
            link_table="student_languages",
            student_ids=student_ids,
            reference_table="languages",
            reference_id="language_code",
            value_column="name",
            catalog_id="code",
        )
        return [*courses, *tags, *languages]

    def _shared_reference_values(
        self,
        *,
        link_table: str,
        student_ids: list[str],
        reference_table: str,
        reference_id: str,
        value_column: str,
        catalog_id: str = "id",
    ) -> list[str]:
        links = execute(
            self.client.table(link_table)
            .select(f"student_id,{reference_id}")
            .in_("student_id", student_ids),
            f"read {link_table}",
        )
        counts = Counter(row[reference_id] for row in links)
        shared_ids = [reference for reference, count in counts.items() if count >= 2]
        if not shared_ids:
            return []
        catalog = execute(
            self.client.table(reference_table)
            .select(f"{catalog_id},{value_column}")
            .in_(catalog_id, shared_ids),
            f"read {reference_table}",
        )
        values = {row[catalog_id]: row[value_column] for row in catalog}
        return [values[item] for item in shared_ids if item in values]
