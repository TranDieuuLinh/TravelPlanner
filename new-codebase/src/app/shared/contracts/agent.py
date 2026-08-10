from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class AgentName(StrEnum):
    supervisor = "supervisor"
    explorer = "explorer"
    information_finder = "information_finder"
    place_checker = "place_checker"
    itinerary_planner = "itinerary_planner"
    plan_editor = "plan_editor"


class AgentTrace(BaseModel):
    agent: AgentName
    status: str = "completed"
    summary: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentError(BaseModel):
    code: str
    message: str
    retryable: bool = False

