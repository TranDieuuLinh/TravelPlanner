from datetime import datetime

from pydantic import Field

from app.modules.place_checker.contract import (
    ContractModel,
    SourcePlaceEvidence,
    UrlNote,
)
from app.modules.place_checker.enums import (
    CostTier,
    OperationalStatus,
    PlaceLifecycleState,
    SourceTier,
    VerificationStatus,
)
from app.modules.place_checker.evaluation_contract import (
    DataQualityEvaluation,
    EvaluationFinding,
    PlaceEvaluation,
    PlannerConstraint,
)
from app.shared.contracts.place import Coordinates


class CheckedDestination(ContractModel):
    adm_id: str | None = None
    compatible: bool | None = None


class CheckedDuration(ContractModel):
    minimum_minutes: int | None = None
    typical_minutes: int | None = None
    maximum_minutes: int | None = None
    known: bool


class CheckedCost(ContractModel):
    tier: CostTier
    currency: str | None = None
    minimum: float | None = None
    typical: float | None = None
    maximum: float | None = None
    known: bool


class CheckedOpening(ContractModel):
    hours: list[str] | None = None
    operational_status: OperationalStatus
    reservation_required: bool | None = None
    known: bool


class CheckedSuitability(ContractModel):
    adults: bool | None = True
    children: bool | None = None
    infants: bool | None = None
    accessibility: list[str] = Field(default_factory=list)


class CheckedVerification(ContractModel):
    status: VerificationStatus
    identity_confidence: float | None = Field(default=None, ge=0, le=1)
    provider: str | None = None
    fetched_at: datetime | None = None


class CheckedEvaluation(ContractModel):
    state: PlaceLifecycleState
    planner_eligible: bool
    preference_matches: list[str] = Field(default_factory=list)
    avoid_conflicts: list[str] = Field(default_factory=list)
    findings: list[EvaluationFinding] = Field(default_factory=list)
    planner_constraints: list[PlannerConstraint] = Field(default_factory=list)
    data_quality: DataQualityEvaluation


class CheckedRanking(ContractModel):
    score: float | None = Field(default=None, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class CheckedProvenance(ContractModel):
    source_places: list[SourcePlaceEvidence] = Field(default_factory=list)
    url_notes: list[UrlNote] = Field(default_factory=list)


class CheckedPlace(ContractModel):
    place_id: str | None = None
    canonical_name: str | None = None
    original_names: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    address: str | None = None
    coordinates: Coordinates | None = None
    destination: CheckedDestination
    source_tier: SourceTier
    mandatory: bool
    removable: bool
    category: str | None = None
    pool_category: str | None = None
    tags: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    duration: CheckedDuration
    cost: CheckedCost
    opening: CheckedOpening
    time_preferences: list[str] = Field(default_factory=list)
    suitability: CheckedSuitability
    verification: CheckedVerification
    evaluation: CheckedEvaluation
    ranking: CheckedRanking
    distance_from_anchor_km: float | None = Field(default=None, ge=0)
    relationship_score: float = Field(default=0, ge=0, le=1)
    provenance: CheckedProvenance
    warnings: list[str] = Field(default_factory=list)
    internal_evaluation: PlaceEvaluation | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )


class GeographicAnalysis(ContractModel):
    known_coordinate_count: int = Field(ge=0)
    unknown_coordinate_count: int = Field(ge=0)
    spread: str
    radius_km: float | None = Field(default=None, ge=0)
    coarse_overhead_minutes: int = Field(default=0, ge=0)
