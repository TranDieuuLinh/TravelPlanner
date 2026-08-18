from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.modules.place_checker.contract import ContractModel
from app.modules.place_checker.resolution_contract import PlaceMetadata


class ResolvedStyleIntent(ContractModel):
    input_value: str = Field(min_length=1, max_length=200)
    source: Literal["style", "item"]
    style_id: str = Field(min_length=1, max_length=200)
    style_name: str = Field(min_length=1, max_length=200)
    item_id: str | None = Field(default=None, max_length=200)
    item_name: str | None = Field(default=None, max_length=200)


class StyleCandidate(ContractModel):
    place_id: str = Field(min_length=1, max_length=200)
    place_name: str = Field(min_length=1, max_length=200)
    entity_type: Literal["TravelPlace", "Restaurant", "DrinkDessert"]
    style_id: str = Field(min_length=1, max_length=200)
    style_name: str = Field(min_length=1, max_length=200)
    item_id: str | None = Field(default=None, max_length=200)
    item_name: str | None = Field(default=None, max_length=200)
    relationship_source: Literal["Offer_Item", "Has_Style"]
    distance_from_anchor_km: float | None = Field(default=None, ge=0)
    metadata: PlaceMetadata


class StyleCandidateSourceBatch(ContractModel):
    resolved_intents: list[ResolvedStyleIntent] = Field(default_factory=list)
    candidates: list[StyleCandidate] = Field(default_factory=list)
    unresolved_style_inputs: list[str] = Field(default_factory=list)
    unresolved_item_inputs: list[str] = Field(default_factory=list)


class StyleCandidateSelection(ContractModel):
    place_id: str = Field(min_length=1, max_length=200)
    place_name: str = Field(min_length=1, max_length=200)
    entity_type: Literal["TravelPlace", "Restaurant", "DrinkDessert"]
    style_id: str = Field(min_length=1, max_length=200)
    style_name: str = Field(min_length=1, max_length=200)
    item_id: str | None = Field(default=None, max_length=200)
    item_name: str | None = Field(default=None, max_length=200)
    relationship_source: Literal["Offer_Item", "Has_Style"]
    distance_from_anchor_km: float | None = Field(default=None, ge=0)
    metadata: PlaceMetadata


class StyleCandidateCoverage(ContractModel):
    style_id: str = Field(min_length=1, max_length=200)
    style_name: str = Field(min_length=1, max_length=200)
    target_candidates: int = Field(ge=0)
    selected_candidates: int = Field(ge=0)
    distinct_items: int = Field(ge=0)
    complete: bool = False
    shortfall_reason: str | None = Field(default=None, max_length=500)


class StyleCandidateSelectionBatch(ContractModel):
    selections: list[StyleCandidateSelection] = Field(default_factory=list)
    coverage: list[StyleCandidateCoverage] = Field(default_factory=list)
    resolved_intents: list[ResolvedStyleIntent] = Field(default_factory=list)
    unresolved_style_inputs: list[str] = Field(default_factory=list)
    unresolved_item_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
