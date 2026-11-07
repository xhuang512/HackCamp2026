from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(tags=["projector"])


class ProjectorState(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"joined_count": 3, "group_count": 1}}
    )

    joined_count: int = Field(ge=0, description="Number of students currently joined")
    group_count: int = Field(ge=0, description="Number of active groups")


@router.get(
    "/projector",
    response_model=ProjectorState,
    summary="Get anonymous projector totals",
    description=(
        "Returns aggregate demo totals only. Student names and timetable details "
        "are intentionally excluded from this public surface."
    ),
)
def get_projector_state() -> ProjectorState:
    return ProjectorState(joined_count=3, group_count=1)
