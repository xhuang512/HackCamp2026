"""POST /admin/reset: put the demo back to its starting state.

Demo mode only, and the same code is deployed twice, once with DEMO_MODE on
for the stage. Step 6 of the demo check in AGENTS.md is this route actually
re-running the seed, which it did not do before: it returned fixed counts and
changed nothing.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client

from app import config, demo, store
from app.db import get_db_client
from app.repositories import RepositoryError

router = APIRouter(prefix="/admin", tags=["admin"])


class ResetResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "reset",
                "seeded_buildings": 8,
                "seeded_students": 60,
                "seeded_groups": 12,
            }
        }
    )

    status: Literal["reset"]
    seeded_buildings: int = Field(ge=0)
    seeded_students: int = Field(ge=0)
    seeded_groups: int = Field(ge=0)


@router.post(
    "/reset",
    response_model=ResetResult,
    summary="Re-run the seed",
    description=(
        "Recreates the seed buildings, students and groups and re-runs "
        "matching. Rows marked is_seed are replaced; real signups survive. "
        "Available only when DEMO_MODE is enabled."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {
            "description": "Demo reset is disabled when DEMO_MODE is not enabled."
        }
    },
)
def reset_demo(
    client: Annotated[Client, Depends(get_db_client)],
) -> ResetResult:
    if not config.DEMO_MODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo reset is disabled",
        )

    # The in-memory identity store goes first. It holds guest profiles, and a
    # guest token only verifies while the student it names exists, so every
    # guest from the last run is signed out by this line.
    store.reset()

    try:
        result = demo.reseed(client)
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not re-run the seed",
        ) from exc

    return ResetResult(
        status="reset",
        seeded_buildings=result.buildings,
        seeded_students=result.students,
        seeded_groups=result.groups,
    )
