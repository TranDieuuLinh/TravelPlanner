from pydantic import BaseModel, Field

from app.modules.information_finder.public import SourceReference
from app.modules.plan_editor.public import EditOperation
from app.modules.supervisor.public import SupervisorRoute
from app.shared.contracts.itinerary import Itinerary
from app.shared.contracts.place import PlaceCandidate


class RootGraphInput(BaseModel):
    request_id: str
    message: str = Field(min_length=1, max_length=4000)
    supplied_candidates: list[PlaceCandidate] = Field(default_factory=list)
    existing_itinerary: Itinerary | None = None
    edit_operation: EditOperation | None = None


class RootGraphOutput(BaseModel):
    request_id: str
    route: SupervisorRoute
    response: str
    itinerary: Itinerary | None = None
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)

