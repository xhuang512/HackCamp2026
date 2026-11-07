from typing import Annotated, Literal

from fastapi import APIRouter, Path
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/groups", tags=["groups"])

GroupResponse = Literal["pending", "joined", "skipped"]


class MeetingSpot(BaseModel):
    building: str
    walk_min: int = Field(ge=0, description="Approximate walking time in minutes")


class SuggestedGroup(BaseModel):
    id: str = Field(description="Opaque group identifier")
    members: list[str] = Field(description="First names visible to the suggested student")
    shared: list[str] = Field(description="Short explanations for why the group matches")
    spot: MeetingSpot
    response: GroupResponse


class GroupResponseUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"group_id": "g_41", "response": "joined"}}
    )

    group_id: str
    response: Literal["joined", "skipped"]


@router.post(
    "/{id}/join",
    response_model=GroupResponseUpdate,
    summary="Join a suggested group",
    description="Records a joined response. This currently returns a mock acknowledgement.",
)
def join_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
) -> GroupResponseUpdate:
    return GroupResponseUpdate(group_id=id, response="joined")


@router.post(
    "/{id}/skip",
    response_model=GroupResponseUpdate,
    summary="Skip a suggested group",
    description="Records a skipped response. This currently returns a mock acknowledgement.",
)
def skip_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
) -> GroupResponseUpdate:
    return GroupResponseUpdate(group_id=id, response="skipped")
