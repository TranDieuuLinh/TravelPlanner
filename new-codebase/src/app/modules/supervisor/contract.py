from typing import Literal

from pydantic import BaseModel, Field


SupervisorRoute = Literal[
    "explorer",
    "information_finder",
    "plan_editor",
    "finish",
]


class SupervisorInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    has_itinerary: bool = False
    has_edit_operation: bool = False


class SupervisorDecision(BaseModel):
    route: SupervisorRoute
    confidence: float = Field(ge=0, le=1)
    reason: str

