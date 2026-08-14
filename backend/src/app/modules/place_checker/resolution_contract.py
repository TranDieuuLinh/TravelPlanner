from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.modules.place_checker.contract import (
    ContractModel,
    PlaceCandidateInput,
    SourcePlaceEvidence,
    SourceTier,
    UrlNote,
)
from app.modules.place_checker.enums import (
    CostTier,
    IdentityResolutionStatus,
    OperationalStatus,
    SimilarityMethod,
)
from app.shared.contracts.place import Coordinates
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.shared.tools.search_places import ProviderAttempt


class CatalogPlace(ContractModel):
    place_id: str = Field(min_length=1, max_length=200)
    canonical_name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    adm_id: str | None = Field(default=None, min_length=1, max_length=200)
    region_key: str | None = Field(default=None, max_length=200)
    country_code: str | None = Field(default=None, min_length=2, max_length=3)
    address: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=120)
    coordinates: Coordinates | None = None
    provider_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    relationships: list[PlaceRelationshipEvidence] = Field(default_factory=list)


class SimilarityComponents(ContractModel):
    lexical_score: float = Field(ge=0, le=1)
    alias_score: float | None = Field(default=None, ge=0, le=1)
    semantic_score: float | None = Field(default=None, ge=0, le=1)
    address_score: float | None = Field(default=None, ge=0, le=1)
    destination_score: float = Field(ge=0, le=1)
    combined_score: float = Field(ge=0, le=1)


class PlaceMatchOption(ContractModel):
    place: CatalogPlace
    method: SimilarityMethod
    components: SimilarityComponents
    # Ranking is global after candidates from several gaps are merged. Each
    # gap is capped separately, so the final rank can legitimately exceed 10.
    rank: int = Field(ge=1)
    eligible_destination: bool
    identity_conflicts: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @property
    def score(self) -> float:
        return self.components.combined_score


class ResolvedPlaceCandidate(ContractModel):
    candidate_index: int = Field(ge=0)
    candidate: PlaceCandidateInput
    status: IdentityResolutionStatus
    selected_place: CatalogPlace | None = None
    match_options: list[PlaceMatchOption] = Field(default_factory=list, max_length=5)
    selected_score: float | None = Field(default=None, ge=0, le=1)
    score_margin: float | None = Field(default=None, ge=0, le=1)
    resolution_method: SimilarityMethod | None = None
    provider_attempts: list[ProviderAttempt] = Field(default_factory=list)
    resolution_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def resolved_candidate_has_identity(self) -> "ResolvedPlaceCandidate":
        if self.status in {
            IdentityResolutionStatus.resolved,
            IdentityResolutionStatus.provisional,
        }:
            if self.selected_place is None or self.selected_score is None:
                raise ValueError(
                    "resolved or provisional candidate requires selected identity and score"
                )
        return self


class IdentityResolutionBatch(ContractModel):
    candidates: list[ResolvedPlaceCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PlaceMetadata(ContractModel):
    place_id: str = Field(min_length=1, max_length=200)
    coordinates: Coordinates | None = None
    address: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=120)
    pool_category: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list)
    image_urls: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    minimum_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    typical_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    maximum_duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    cost_tier: CostTier = CostTier.unknown
    cost_currency: str | None = Field(default=None, min_length=3, max_length=3)
    minimum_cost: float | None = Field(default=None, ge=0)
    typical_cost: float | None = Field(default=None, ge=0)
    maximum_cost: float | None = Field(default=None, ge=0)
    opening_hours: list[str] | None = None
    operational_status: OperationalStatus = OperationalStatus.unknown
    reservation_required: bool | None = None
    accessibility: list[str] = Field(default_factory=list)
    children_suitable: bool | None = None
    infants_suitable: bool | None = None
    source: str | None = Field(default=None, max_length=120)
    fetched_at: datetime | None = None
    relationships: list[PlaceRelationshipEvidence] = Field(default_factory=list)


class EnrichedIdentityPlace(ContractModel):
    place_id: str | None = None
    canonical_name: str | None = None
    original_names: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    source_tier: SourceTier
    mandatory: bool
    removable: bool
    status: IdentityResolutionStatus
    identity_confidence: float | None = Field(default=None, ge=0, le=1)
    metadata: PlaceMetadata | None = None
    source_places: list[SourcePlaceEvidence] = Field(default_factory=list)
    url_notes: list[UrlNote] = Field(default_factory=list)
    match_options: list[PlaceMatchOption] = Field(default_factory=list)
    evidence_conflicts: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceEnrichmentOutput(ContractModel):
    places: list[EnrichedIdentityPlace] = Field(default_factory=list)
    unattached_url_notes: list[UrlNote] = Field(default_factory=list)
    duplicate_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
