from typing import Literal

from fastapi import APIRouter, status
from pydantic import BaseModel, ConfigDict, Field

from app.routers.groups import MeetingSpot, SuggestedGroup

router = APIRouter(tags=["students"])


class StudentCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Maya",
                "tags": ["transfer"],
                "languages": ["English", "Korean"],
                "courses": ["STAT 302"],
                "preset_schedule": "tue_thu_afternoon",
            }
        }
    )

    first_name: str = Field(min_length=1, max_length=80, description="Student's first name")
    tags: list[str] = Field(default_factory=list, description="Lightweight matching tags")
    languages: list[str] = Field(default_factory=list, description="Languages the student speaks")
    courses: list[str] = Field(default_factory=list, description="Current course codes")
    preset_schedule: str = Field(
        min_length=1,
        description="Frontend-defined key for a preset schedule",
        examples=["tue_thu_afternoon"],
    )


class StudentSession(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "student_id": "s_demo_01",
                "first_name": "Maya",
                "session_token": "guest_demo_session",
                "is_guest": True,
            }
        }
    )

    student_id: str = Field(description="Opaque student identifier")
    first_name: str
    session_token: str = Field(description="Temporary guest session credential")
    is_guest: bool


class Gap(BaseModel):
    day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["13:00"])
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", examples=["15:00"])


class CurrentSuggestionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "gap": {"day": "tue", "start": "13:00", "end": "15:00"},
                "group": {
                    "id": "g_41",
                    "members": ["Ji-woo", "Amir", "Rosa"],
                    "shared": ["STAT 302", "2 transfers", "Korean"],
                    "spot": {"building": "The Nest", "walk_min": 4},
                    "response": "pending",
                },
            }
        }
    )

    gap: Gap
    group: SuggestedGroup

    @classmethod
    def mock(cls) -> "CurrentSuggestionResponse":
        return cls(
            gap=Gap(day="tue", start="13:00", end="15:00"),
            group=SuggestedGroup(
                id="g_41",
                members=["Ji-woo", "Amir", "Rosa"],
                shared=["STAT 302", "2 transfers", "Korean"],
                spot=MeetingSpot(building="The Nest", walk_min=4),
                response="pending",
            ),
        )


@router.post(
    "/students",
    response_model=StudentSession,
    status_code=status.HTTP_201_CREATED,
    summary="Create a demo student",
    description=(
        "Creates a student from onboarding details and returns a guest session. "
        "This walking-skeleton implementation returns a fixed mock identity."
    ),
)
def create_student(student: StudentCreate) -> StudentSession:
    return StudentSession(
        student_id="s_demo_01",
        first_name=student.first_name,
        session_token="guest_demo_session",
        is_guest=True,
    )


@router.get(
    "/me/now",
    response_model=CurrentSuggestionResponse,
    summary="Get the current group suggestion",
    description=(
        "Returns the student's next timetable gap and one deterministic group "
        "suggestion. Authentication and matching are not implemented yet."
    ),
)
def get_current_suggestion() -> CurrentSuggestionResponse:
    return CurrentSuggestionResponse.mock()
