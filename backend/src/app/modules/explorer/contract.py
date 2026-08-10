from pydantic import BaseModel, Field

from app.shared.contracts.place import PlaceCandidate
from app.shared.contracts.trip import TripIntent


class ExplorerInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    supplied_candidates: list[PlaceCandidate] = Field(default_factory=list)


class ExplorerOutput(BaseModel):
    intent: TripIntent | None = None
    candidates: list[PlaceCandidate] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_question: str | None = None

