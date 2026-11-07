from typing import Any

from app.repositories.base import RecordNotFoundError, execute


class BuildingRepository:
    def __init__(self, client: Any):
        self.client = client

    def first_available(self) -> dict[str, Any]:
        rows = execute(
            self.client.table("buildings").select("id,name").order("id").limit(1),
            "read meeting buildings",
        )
        if not rows:
            raise RecordNotFoundError(
                "No buildings exist; add a valid meeting building before matching"
            )
        return rows[0]
