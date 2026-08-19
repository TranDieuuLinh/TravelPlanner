from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.shared.contracts.user_context import UserContextRequest


SupervisorRoute = Literal[
    "explorer",
    "information_finder",
    "plan_editor",
    "finish",
]


class SupervisorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=4000)
    conversation_context: list[str] = Field(default_factory=list, max_length=6)
    has_source_input: bool = False
    has_itinerary: bool = False
    has_edit_operation: bool = False

    destination: str | None = Field(default=None, max_length=200)
    duration_days: int | None = Field(default=None, ge=1, le=60)
    mentioned_places: list[str] = Field(default_factory=list, max_length=50)
    selected_places: list[str] = Field(default_factory=list, max_length=50)
    clarification_required: bool = False
    user_context_requests: list[UserContextRequest] = Field(
        default_factory=list, max_length=20
    )
    pending_user_context: list[UserContextRequest] = Field(
        default_factory=list, max_length=20
    )
    conversation_summary: str | None = Field(default=None, max_length=2000)


class ClassifierResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: SupervisorRoute
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=240)
    response: str | None = Field(default=None, max_length=1000)


class SupervisorDecision(ClassifierResult):
    clarification_question: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=10)
