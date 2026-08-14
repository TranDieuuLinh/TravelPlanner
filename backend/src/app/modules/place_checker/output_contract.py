from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.modules.place_checker.analysis_contract import (
    BudgetAnalysis,
    CapacityAnalysis,
    CoverageAnalysis,
    GapAnalysis,
    TripAggregateAnalysis,
)
from app.modules.place_checker.checked_output_contract import (
    CheckedPlace,
    GeographicAnalysis,
)
from app.modules.place_checker.contract import (
    ContractModel,
    SourcePlaceEvidence,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import (
    CostTier,
    OperationalStatus,
    PlaceCheckerStatus,
    PlaceLifecycleState,
    SourceTier,
    UnresolvedEntityType,
    VerificationStatus,
)
from app.modules.place_checker.evaluation_contract import PlannerConstraint
from app.modules.place_checker.food_selection_contract import SelectedFoodRestaurant
from app.modules.place_checker.item_contract import ResolvedInputItem, SpecialExperience
from app.modules.place_checker.retrieval_contract import RetrievalBatch
from app.modules.place_checker.scoring_contract import (
    CandidateRankingBatch,
)
from app.shared.contracts.place import Coordinates


class UnresolvedEntity(ContractModel):
    entity_type: UnresolvedEntityType
    input_index: int | None = Field(default=None, ge=0)
    input_name: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    mandatory: bool = False


class ToolCallSummary(ContractModel):
    adm_resolver: int = Field(default=0, ge=0)
    search_places_named: int = Field(default=0, ge=0)
    search_places_requirement: int = Field(default=0, ge=0)
    retrieval_search: int = Field(default=0, ge=0)
    external_search: int = Field(default=0, ge=0)
    metadata_repository: int = Field(default=0, ge=0)
    food_selection: int = Field(default=0, ge=0)


class PlaceCheckerExecutionMetadata(ContractModel):
    request_id: str = Field(min_length=1, max_length=200)
    correlation_id: str = Field(min_length=1, max_length=200)
    place_checker_version: str = "place_checker.v1"
    generated_at: datetime
    duration_ms: int = Field(default=0, ge=0)
    phase_duration_ms: dict[str, int] = Field(default_factory=dict)
    tool_calls: ToolCallSummary = Field(default_factory=ToolCallSummary)
    partial: bool = False
    sample_data: bool = False

    @property
    def schema_version(self) -> str:
        return self.place_checker_version


class PlaceCheckerResult(ContractModel):
    schema_version: str = "place_checker.v1"
    status: PlaceCheckerStatus
    trip_context: TripEvaluationContext
    checked_places: list[CheckedPlace] = Field(default_factory=list)
    planner_eligible_place_ids: list[str] = Field(default_factory=list)
    resolved_items: list[ResolvedInputItem] = Field(default_factory=list)
    special_experiences: list[SpecialExperience] = Field(default_factory=list)
    food_restaurant_selections: list[SelectedFoodRestaurant] = Field(
        default_factory=list
    )
    budget_analysis: BudgetAnalysis
    capacity_analysis: CapacityAnalysis
    coverage_analysis: CoverageAnalysis
    geographic_analysis: GeographicAnalysis
    gap_analysis: GapAnalysis
    retrieval: RetrievalBatch | None = Field(default=None, exclude=True)
    ranking: CandidateRankingBatch | None = Field(default=None, exclude=True)
    unresolved_entities: list[UnresolvedEntity] = Field(default_factory=list)
    planner_constraints: list[PlannerConstraint] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: PlaceCheckerExecutionMetadata

    @property
    def aggregate_analysis(self) -> TripAggregateAnalysis:
        return TripAggregateAnalysis(
            budget=self.budget_analysis,
            capacity=self.capacity_analysis,
            coverage=self.coverage_analysis,
            gaps=self.gap_analysis,
        )


class PlannerPlaceContext(ContractModel):
    place_id: str
    canonical_name: str
    coordinates: Coordinates
    address: str | None = None
    state: PlaceLifecycleState
    source_tier: SourceTier
    mandatory: bool
    removable: bool
    category: str | None = None
    pool_category: str | None = None
    tags: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    distance_from_anchor_km: float | None = Field(default=None, ge=0)
    relationship_score: float = Field(default=0, ge=0, le=1)
    relationships: list[str] = Field(default_factory=list)
    minimum_duration_minutes: int | None = Field(default=None, ge=1)
    typical_duration_minutes: int | None = Field(default=None, ge=1)
    maximum_duration_minutes: int | None = Field(default=None, ge=1)
    cost_tier: CostTier = CostTier.unknown
    minimum_cost: float | None = Field(default=None, ge=0)
    typical_cost: float | None = Field(default=None, ge=0)
    maximum_cost: float | None = Field(default=None, ge=0)
    currency: str | None = None
    opening_hours: list[str] | None = None
    operational_status: OperationalStatus = OperationalStatus.unknown
    reservation_required: bool | None = None
    time_preferences: list[str] = Field(default_factory=list)
    adults_suitable: bool | None = None
    children_suitable: bool | None = None
    infants_suitable: bool | None = None
    accessibility: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus
    identity_confidence: float | None = Field(default=None, ge=0, le=1)
    score: float | None = Field(default=None, ge=0, le=1)
    constraints: list[PlannerConstraint] = Field(default_factory=list)
    provenance: list[SourcePlaceEvidence] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class PlaceCheckerPlanningProjection(ContractModel):
    destination_adm_id: str
    places: list[PlannerPlaceContext] = Field(default_factory=list)
    resolved_items: list[ResolvedInputItem] = Field(default_factory=list)
    special_experiences: list[SpecialExperience] = Field(default_factory=list)
    blocked_mandatory_place_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerPrice(ContractModel):
    cost: float = Field(ge=0)
    currency: str = "VND"


class PlannerBudget(ContractModel):
    amount: float | None = Field(default=None, ge=0)
    currency: str = "VND"


class PlannerTimeWindow(ContractModel):
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=0, le=1440)


class PlannerOutputPlace(ContractModel):
    place_id: str
    name: str
    coordinates: Coordinates
    address: str | None = None
    priority: Literal[
        "user_input", "url", "special_experience", "special_near"
    ]
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    duration_minutes: int = Field(ge=1)
    opening_hours: dict[str, list[PlannerTimeWindow]] | None = None
    preferred_time_windows: list[PlannerTimeWindow] = Field(default_factory=list)
    source_kind: Literal[
        "special_experience", "offer_item", "both", "generic"
    ] = "generic"
    offered_activity_ids: list[str] = Field(default_factory=list)
    time_source: Literal[
        "place", "activity_item", "has_style", "source_hint", "unknown"
    ] = "unknown"
    price: PlannerPrice
    relationships: list[str] = Field(default_factory=list)


class PlannerOutputFood(PlannerOutputPlace):
    supported_meals: list[Literal["breakfast", "lunch", "dinner"]] = Field(
        min_length=1
    )


class PlannerOutputAccommodation(ContractModel):
    place_id: str
    name: str
    address: str | None = None
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int | None = Field(default=None, ge=0)
    price_per_night: PlannerPrice


class PlannerOutputTrip(ContractModel):
    destination: str
    days: int = Field(ge=1)
    start_date: str
    timezone: str
    people: int = Field(ge=1)
    budget: PlannerBudget
    preferences: list[str] = Field(default_factory=list)


class PlaceCheckerPlannerOutput(ContractModel):
    trip: PlannerOutputTrip
    places: list[PlannerOutputPlace] = Field(default_factory=list)
    food: list[PlannerOutputFood] = Field(default_factory=list)
    accommodation: PlannerOutputAccommodation | None = None
