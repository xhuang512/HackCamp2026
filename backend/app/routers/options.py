from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from supabase import Client

from app.db import get_db_client
from app.repositories import RepositoryError
from app.repositories.buildings import BuildingRepository
from app.repositories.reference_data import ReferenceDataRepository

router = APIRouter(tags=["options"])


class ReferenceOption(BaseModel):
    id: str = Field(description="Canonical identifier accepted by POST /students")
    label: str = Field(description="Human-readable dropdown label")


class OnboardingOptions(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "languages": [{"id": "en", "label": "English"}],
                "tags": [{"id": "transfer", "label": "Transfer student"}],
                "buildings": [{"id": "nest", "label": "The Nest"}],
            }
        }
    )

    languages: list[ReferenceOption]
    tags: list[ReferenceOption]
    buildings: list[ReferenceOption]


@router.get(
    "/options",
    response_model=OnboardingOptions,
    summary="List controlled onboarding options",
    description=(
        "Returns canonical language codes and student-type tag slugs supported "
        "by POST /students, plus the meeting-building slugs accepted by "
        "POST /groups."
    ),
)
def get_options(
    client: Annotated[Client, Depends(get_db_client)],
) -> OnboardingOptions:
    repository = ReferenceDataRepository(client)
    try:
        languages = repository.list_languages()
        tags = repository.list_student_tags()
        buildings = BuildingRepository(client).list_all()
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not load onboarding options",
        ) from exc
    return OnboardingOptions(
        languages=[
            ReferenceOption(id=str(row["code"]), label=str(row["name"]))
            for row in languages
        ],
        tags=[
            ReferenceOption(id=str(row["slug"]), label=str(row["label"]))
            for row in tags
        ],
        buildings=[
            ReferenceOption(id=str(row["slug"]), label=str(row["name"]))
            for row in buildings
        ],
    )
