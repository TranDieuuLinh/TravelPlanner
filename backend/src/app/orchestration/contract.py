from typing import Any

from pydantic import BaseModel, Field

from app.modules.conversation_memory.public import (
    MemoryReference,
    WorkingMemoryState,
)
from app.modules.explorer.public import ExplorerImageInput
from app.modules.explorer.public import ExplorerOutput
from app.modules.information_finder.public import SourceReference
from app.modules.itinerary_planner.public import ItineraryPlannerOutput
from app.modules.plan_editor.public import EditOperation
from app.modules.supervisor.public import SupervisorRoute
from app.shared.contracts.itinerary import Itinerary


class RootGraphInput(BaseModel):
    request_id: str
    message: str = Field(default="", max_length=4000)
    urls: list[str] = Field(default_factory=list, max_length=20)
    images: list[ExplorerImageInput] = Field(default_factory=list, max_length=20)
    force_refresh: bool = False
    existing_itinerary: Itinerary | None = None
    existing_planner_output: dict[str, Any] | None = None
    edit_operation: EditOperation | None = None
    explorer_output: ExplorerOutput | None = None

    recent_messages: list[str] = Field(default_factory=list, max_length=20)
    conversation_summary: str | None = None
    resolved_references: list[MemoryReference] = Field(default_factory=list)


class RootGraphOutput(BaseModel):
    request_id: str
    route: SupervisorRoute
    response: str
    itinerary: Itinerary | None = None
    planner_output: ItineraryPlannerOutput | None = None
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
