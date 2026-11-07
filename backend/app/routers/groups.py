from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client

from app.auth import get_current_student_id
from app.db import get_db_client
from app.repositories import RecordNotFoundError, RepositoryError
from app.repositories.group_members import GroupMemberRepository

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
    description="Persists a joined response for the authenticated student.",
)
def join_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _update_response(client, id, student_id, "joined")


@router.post(
    "/{id}/skip",
    response_model=GroupResponseUpdate,
    summary="Skip a suggested group",
    description="Persists a skipped response for the authenticated student.",
)
def skip_group(
    id: Annotated[str, Path(description="Opaque group identifier", examples=["g_41"])],
    student_id: Annotated[str, Depends(get_current_student_id)],
    client: Annotated[Client, Depends(get_db_client)],
) -> GroupResponseUpdate:
    return _update_response(client, id, student_id, "skipped")


def _update_response(
    client: Client,
    group_id: str,
    student_id: str,
    response: Literal["joined", "skipped"],
) -> GroupResponseUpdate:
    try:
        GroupMemberRepository(client).update_response(group_id, student_id, response)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not update group membership",
        ) from exc
    return GroupResponseUpdate(group_id=group_id, response=response)
