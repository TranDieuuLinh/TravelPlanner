from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SupervisorRoute = Literal[
    "explorer",
    "information_finder",
    "plan_editor",
    "finish",
]


class SupervisorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    has_itinerary: bool = False
    has_edit_operation: bool = False


class ClassifierResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: SupervisorRoute
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=240)
    response: str | None = Field(default=None, max_length=1000)


class SupervisorDecision(ClassifierResult):
    clarification_question: str | None = Field(default=None, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=10)
