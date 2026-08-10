from typing import Literal

from pydantic import BaseModel, Field

from app.shared.contracts.place import PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent


CoverageStatus = Literal["sufficient", "insufficient"]


class PlaceCheckerInput(BaseModel):
    intent: TripIntent
    candidates: list[PlaceCandidate] = Field(default_factory=list)


class PlaceCheckerOutput(BaseModel):
    places: list[VerifiedPlace] = Field(default_factory=list)
    rejected_candidates: list[PlaceCandidate] = Field(default_factory=list)
    coverage_status: CoverageStatus
    warnings: list[str] = Field(default_factory=list)

