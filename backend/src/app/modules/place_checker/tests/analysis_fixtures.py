from datetime import UTC, datetime
from decimal import Decimal

from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    BudgetInput,
    CapacityRange,
    InputItem,
    PeopleInput,
    SourcePlaceEvidence,
    TravelPace,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import (
    BudgetMode,
    CostTier,
    EvidenceOrigin,
    IdentityResolutionStatus,
    ItemResolutionStatus,
    OperationalStatus,
    PlaceLifecycleState,
    SourceTier,
)
from app.modules.place_checker.evaluation_contract import (
    DataQualityEvaluation,
    EvaluationFinding,
    PeopleSuitabilityEvaluation,
    PlaceEvaluation,
    PlaceEvaluationBatch,
    PlannerConstraint,
)
from app.modules.place_checker.item_contract import (
    ItemResolutionBatch,
    ResolvedInputItem,
)
from app.modules.place_checker.resolution_contract import (
    EnrichedIdentityPlace,
    PlaceMetadata,
)
from app.shared.contracts.place import Coordinates


NOW = datetime(2026, 8, 11, tzinfo=UTC)


def analysis_context(
    *,
    level: str = "low",
    target_amount: Decimal | None = None,
    capacity: CapacityRange | None = None,
    days: int = 2,
) -> TripEvaluationContext:
    return TripEvaluationContext(
        destination=AdmResolution(
            input_name="Hanoi",
            status=AdmResolutionStatus.resolved,
            adm_id="adm1_vn_ha_noi",
            canonical_name="Hà Nội",
            country_code="VN",
            region_key="vn,ha_noi",
        ),
        days=days,
        pace=TravelPace.balanced,
        capacity=capacity
        or CapacityRange(
            minimum_minutes=360,
            typical_minutes=480,
            maximum_minutes=600,
        ),
        budget_mode=(
            BudgetMode.target_amount
            if target_amount is not None
            else BudgetMode.relative_level
        ),
        budget=BudgetInput(
            level=level,
            target_amount=target_amount,
            currency="VND",
            source="test",
        ),
        people=PeopleInput(adults=1, children=0, infants=0),
        preferences=[],
        avoids=[],
    )


def evaluated_place(
    place_id: str,
    *,
    mandatory: bool = True,
    source_tier: SourceTier | None = None,
    category: str = "landmark",
    cost_tier: CostTier = CostTier.low,
    minimum_cost: float | None = None,
    typical_cost: float | None = None,
    maximum_cost: float | None = None,
    currency: str | None = "VND",
    minimum_duration: int | None = 60,
    typical_duration: int | None = 90,
    maximum_duration: int | None = 120,
    coordinates: Coordinates | None = None,
    planner_eligible: bool = True,
    state: PlaceLifecycleState | None = None,
    destination_compatible: bool | None = True,
    missing_fields: list[str] | None = None,
    findings: list[EvaluationFinding] | None = None,
    constraints: list[PlannerConstraint] | None = None,
    evidence_conflicts: list[str] | None = None,
) -> PlaceEvaluation:
    tier = source_tier or (
        SourceTier.direct_user if mandatory else SourceTier.url
    )
    coordinates = coordinates or Coordinates(latitude=21.03, longitude=105.84)
    metadata = PlaceMetadata(
        place_id=place_id,
        coordinates=coordinates,
        category=category,
        tags=[category],
        minimum_duration_minutes=minimum_duration,
        typical_duration_minutes=typical_duration,
        maximum_duration_minutes=maximum_duration,
        cost_tier=cost_tier,
        cost_currency=currency,
        minimum_cost=minimum_cost,
        typical_cost=typical_cost,
        maximum_cost=maximum_cost,
        opening_hours=["09:00-17:00"],
        operational_status=OperationalStatus.active,
        reservation_required=False,
        children_suitable=True,
        infants_suitable=True,
        source="knowledge_graph",
        fetched_at=NOW,
    )
    origin = EvidenceOrigin.input if mandatory else EvidenceOrigin.url
    place = EnrichedIdentityPlace(
        place_id=place_id,
        canonical_name=f"Place {place_id}",
        original_names=[f"Place {place_id}"],
        source_tier=tier,
        mandatory=mandatory,
        removable=not mandatory,
        status=IdentityResolutionStatus.resolved,
        identity_confidence=0.95,
        metadata=metadata,
        source_places=[
            SourcePlaceEvidence(
                origin=origin,
                evidence_type="test",
                evidence=f"Visit {place_id}",
            )
        ],
        evidence_conflicts=evidence_conflicts or [],
    )
    missing = missing_fields or []
    return PlaceEvaluation(
        place=place,
        state=state
        or (
            PlaceLifecycleState.planner_ready
            if planner_eligible
            else PlaceLifecycleState.rejected
        ),
        planner_eligible=planner_eligible,
        destination_compatible=destination_compatible,
        people_suitability=PeopleSuitabilityEvaluation(
            children=True,
            infants=True,
        ),
        data_quality=DataQualityEvaluation(
            completeness_score=(7 - len(missing)) / 7,
            missing_fields=missing,
        ),
        findings=findings or [],
        planner_constraints=constraints or [],
    )


def place_batch(*places: PlaceEvaluation) -> PlaceEvaluationBatch:
    return PlaceEvaluationBatch(
        places=list(places),
        planner_eligible_place_ids=[
            place.place.place_id for place in places if place.planner_eligible
        ],
    )


def empty_items() -> ItemResolutionBatch:
    return ItemResolutionBatch()


def unresolved_item(
    index: int,
    *,
    name: str,
    item_type: str,
) -> ResolvedInputItem:
    item = InputItem(
        name=name,
        item_type=item_type,
        action="experience",
        evidence=name,
        confidence=0.9,
    )
    return ResolvedInputItem(
        item_index=index,
        item=item,
        normalized_requirement=name,
        status=ItemResolutionStatus.unresolved,
        evidence=name,
    )
