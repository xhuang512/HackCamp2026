from collections import Counter
from typing import Any

from app.repositories.base import ReferenceDataError, RepositoryError, execute


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

    def delete(self, student_id: str) -> None:
        execute(
            self.client.table("students").delete().eq("id", student_id),
            "roll back student creation",
        )

    def add_tags(self, student_id: str, slugs: list[str]) -> None:
        if not slugs:
            return
        rows = execute(
            self.client.table("tags").select("id,slug").in_("slug", slugs),
            "resolve student tags",
        )
        by_slug = {row["slug"]: row["id"] for row in rows}
        self._require_all("tags", slugs, by_slug)
        execute(
            self.client.table("student_tags").insert(
                [
                    {"student_id": student_id, "tag_id": by_slug[slug]}
                    for slug in dict.fromkeys(slugs)
                ]
            ),
            "create student tags",
        )

    def add_languages(self, student_id: str, names: list[str]) -> None:
        if not names:
            return
        rows = execute(
            self.client.table("languages").select("code,name").in_("name", names),
            "resolve student languages",
        )
        by_name = {row["name"]: row["code"] for row in rows}
        self._require_all("languages", names, by_name)
        execute(
            self.client.table("student_languages").insert(
                [
                    {
                        "student_id": student_id,
                        "language_code": by_name[name],
                    }
                    for name in dict.fromkeys(names)
                ]
            ),
            "create student languages",
        )

    def add_courses(self, student_id: str, codes: list[str], term: str) -> None:
        if not codes:
            return
        rows = execute(
            self.client.table("courses").select("id,code").in_("code", codes),
            "resolve student courses",
        )
        by_code = {row["code"]: row["id"] for row in rows}
        self._require_all("courses", codes, by_code)
        execute(
            self.client.table("student_courses").insert(
                [
                    {
                        "student_id": student_id,
                        "course_id": by_code[code],
                        "term": term,
                    }
                    for code in dict.fromkeys(codes)
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

    @staticmethod
    def _require_all(kind: str, requested: list[str], found: dict[str, Any]) -> None:
        missing = [value for value in dict.fromkeys(requested) if value not in found]
        if missing:
            raise ReferenceDataError(
                f"Unknown {kind}: {', '.join(missing)}"
            )
