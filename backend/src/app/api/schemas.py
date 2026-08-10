from pydantic import BaseModel, Field

from app.modules.plan_editor.public import EditOperation
from app.shared.contracts.itinerary import Itinerary
from app.shared.contracts.place import PlaceCandidate


class InvokeRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4000)
    supplied_candidates: list[PlaceCandidate] = Field(default_factory=list)
    existing_itinerary: Itinerary | None = None
    edit_operation: EditOperation | None = None


class InvokeResponse(BaseModel):
    request_id: str
    route: str
    response: str
    itinerary: Itinerary | None = None
    clarification_question: str | None = None
    warnings: list[str] = Field(default_factory=list)

