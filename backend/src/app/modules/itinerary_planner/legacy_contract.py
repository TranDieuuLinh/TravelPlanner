"""Temporary contract for the pre-Phase-2 compatibility graph.

The root graph still invokes the scaffold planner. Checkpoint A deliberately does
not connect the new public boundary to runtime; this model can be removed at the
integration checkpoint.
"""

from pydantic import BaseModel, Field

from app.shared.contracts.place import VerifiedPlace
from app.shared.contracts.trip import TripIntent


class LegacyItineraryPlannerInput(BaseModel):
    intent: TripIntent
    places: list[VerifiedPlace] = Field(default_factory=list)
    upstream_warnings: list[str] = Field(default_factory=list)
