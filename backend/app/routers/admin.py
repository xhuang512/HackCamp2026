import os
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/admin", tags=["admin"])


class ResetResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "reset", "seeded_students": 4, "seeded_groups": 1}
        }
    )

    status: Literal["reset"]
    seeded_students: int = Field(ge=0)
    seeded_groups: int = Field(ge=0)


@router.post(
    "/reset",
    response_model=ResetResult,
    summary="Reset demo seed data",
    description=(
        "Acknowledges a demo reset when DEMO_MODE is enabled. No data is currently "
        "changed because persistence is not part of the initial mock contract."
    ),
    responses={
        status.HTTP_403_FORBIDDEN: {
            "description": "Demo reset is disabled when DEMO_MODE is not enabled."
        }
    },
)
def reset_demo() -> ResetResult:
    demo_mode = os.getenv("DEMO_MODE", "").lower() in {"1", "true", "yes", "on"}
    if not demo_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo reset is disabled",
        )
    return ResetResult(status="reset", seeded_students=4, seeded_groups=1)
