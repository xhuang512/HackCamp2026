from typing import Any

from app.repositories.base import RecordNotFoundError, execute

# Every column the map and the meeting spot need. Kept in one place because
# three callers select the same shape.
COLUMNS = "id,slug,name,lat,lng,is_indoor"


class BuildingRepository:
    def __init__(self, client: Any):
        self.client = client

    def list_all(self) -> list[dict[str, Any]]:
        """Every meetable building. The map draws from this, and pick_spot
        chooses from it, so an empty table means an empty map."""
        return execute(
            self.client.table("buildings").select(COLUMNS).order("id"),
            "read buildings",
        )

    def by_slug(self, slug: str) -> dict[str, Any]:
        rows = execute(
            self.client.table("buildings").select(COLUMNS).eq("slug", slug).limit(1),
            "read building by slug",
        )
        if not rows:
            raise RecordNotFoundError(f"No building with slug {slug!r}")
        return rows[0]
