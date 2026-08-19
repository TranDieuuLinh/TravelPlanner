from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from app.modules.place_checker.contract import ContractModel


RelationshipDirection = Literal[
    "place_to_place",
    "place_to_attribute",
    "area_to_place",
]
RelationshipScope = Literal["anchor", "destination", "place"]


class PlaceRelationshipEvidence(ContractModel):
    """Normalized, planner-safe evidence derived from a Knowledge Graph edge."""

    relationship_type: str = Field(min_length=1, max_length=100)
    direction: RelationshipDirection
    scope: RelationshipScope
    from_entity_id: str = Field(min_length=1, max_length=200)
    to_entity_id: str = Field(min_length=1, max_length=200)
    related_entity_id: str | None = Field(default=None, max_length=200)
    related_name: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=40)
    confidence: float | None = Field(default=None, ge=0, le=1)
    priority: float | None = None
    distance_km: float | None = Field(default=None, ge=0)
    threshold_km: float | None = Field(default=None, gt=0)
    source: str | None = Field(default=None, max_length=2000)
    source_note: str | None = Field(default=None, max_length=4000)
    properties: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(default=0, ge=0, le=1)

    @property
    def is_pending(self) -> bool:
        return (self.status or "").casefold() == "pending"
