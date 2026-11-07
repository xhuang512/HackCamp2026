import re
from typing import Any, Iterable

from app.repositories.base import ReferenceDataError, RepositoryError, execute


DEFAULT_LANGUAGES: tuple[dict[str, str], ...] = (
    {"code": "en", "name": "English"},
    {"code": "fr", "name": "French"},
    {"code": "es", "name": "Spanish"},
    {"code": "zh", "name": "Mandarin Chinese"},
    {"code": "yue", "name": "Cantonese"},
    {"code": "ko", "name": "Korean"},
    {"code": "ja", "name": "Japanese"},
    {"code": "hi", "name": "Hindi"},
    {"code": "pa", "name": "Punjabi"},
)

DEFAULT_STUDENT_TAGS: tuple[dict[str, str], ...] = (
    {"slug": "international", "label": "International student"},
    {"slug": "transfer", "label": "Transfer student"},
    {"slug": "exchange", "label": "Exchange student"},
    {"slug": "commuter", "label": "Commuter"},
    {"slug": "resident", "label": "Residence student"},
    {"slug": "graduate", "label": "Graduate student"},
    {"slug": "first-term", "label": "First term at UBC"},
)

COURSE_CODE_PATTERN = re.compile(r"^([A-Z]{2,5})([0-9]{3}[A-Z]?)$")


class ReferenceDataRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_languages(self) -> list[dict[str, Any]]:
        return execute(
            self.client.table("languages")
            .select("code,name")
            .order("name"),
            "list supported languages",
        )

    def list_student_tags(self) -> list[dict[str, Any]]:
        return execute(
            self.client.table("tags")
            .select("id,slug,label,category")
            .eq("category", "student_type")
            .order("label"),
            "list supported student tags",
        )

    def seed_defaults(self) -> tuple[int, int]:
        languages = execute(
            self.client.table("languages").upsert(
                list(DEFAULT_LANGUAGES),
                on_conflict="code",
            ),
            "seed supported languages",
        )
        tags = execute(
            self.client.table("tags").upsert(
                [
                    {**tag, "category": "student_type"}
                    for tag in DEFAULT_STUDENT_TAGS
                ],
                on_conflict="slug",
            ),
            "seed supported student tags",
        )
        return len(languages), len(tags)

    def resolve_languages(self, values: list[str]) -> list[str]:
        if not values:
            return []
        rows = self.list_languages()
        by_code = {str(row["code"]).casefold(): str(row["code"]) for row in rows}
        by_name = {str(row["name"]).casefold(): str(row["code"]) for row in rows}
        resolved: list[str] = []
        missing: list[str] = []
        for value in values:
            cleaned = value.strip()
            code = by_code.get(cleaned.casefold()) or by_name.get(cleaned.casefold())
            if code is None:
                missing.append(value)
            elif code not in resolved:
                resolved.append(code)
        if missing:
            raise ReferenceDataError(
                f"Unknown languages: {', '.join(dict.fromkeys(missing))}"
            )
        return resolved

    def resolve_tags(self, values: list[str]) -> dict[str, int]:
        if not values:
            return {}
        normalized = [value.strip().lower() for value in values]
        rows = self.list_student_tags()
        by_slug = {str(row["slug"]): int(row["id"]) for row in rows}
        missing = [
            value for value in dict.fromkeys(normalized) if value not in by_slug
        ]
        if missing:
            raise ReferenceDataError(f"Unknown tags: {', '.join(missing)}")
        return {slug: by_slug[slug] for slug in dict.fromkeys(normalized)}

    def resolve_or_create_courses(self, values: Iterable[str]) -> dict[str, int]:
        codes = normalize_course_codes(values)
        if not codes:
            return {}
        existing = execute(
            self.client.table("courses")
            .select("id,code")
            .in_("code", codes),
            "resolve student courses",
        )
        by_code = {str(row["code"]): int(row["id"]) for row in existing}
        missing = [code for code in codes if code not in by_code]
        if missing:
            execute(
                self.client.table("courses").upsert(
                    [{"code": code} for code in missing],
                    on_conflict="code",
                ),
                "create student courses",
            )
            resolved = execute(
                self.client.table("courses")
                .select("id,code")
                .in_("code", codes),
                "reload student courses",
            )
            by_code = {str(row["code"]): int(row["id"]) for row in resolved}
        unresolved = [code for code in codes if code not in by_code]
        if unresolved:
            raise RepositoryError(
                f"Database did not return courses: {', '.join(unresolved)}"
            )
        return {code: by_code[code] for code in codes}


def normalize_course_code(value: str) -> str:
    compact = re.sub(r"[\s-]+", "", value.strip().upper())
    match = COURSE_CODE_PATTERN.fullmatch(compact)
    if match is None:
        raise ReferenceDataError(
            f"Invalid course code '{value}'; expected a code such as STAT 406"
        )
    return f"{match.group(1)} {match.group(2)}"


def normalize_course_codes(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(normalize_course_code(value) for value in values))
