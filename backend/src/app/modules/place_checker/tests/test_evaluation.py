from datetime import UTC, datetime, timedelta

from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    BudgetInput,
    CapacityRange,
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
    OperationalStatus,
    PlaceLifecycleState,
    SimilarityMethod,
    SourceTier,
)
from app.modules.place_checker.evaluation import PlaceEvaluationService
from app.modules.place_checker.resolution_contract import (
    CatalogPlace,
    EnrichedIdentityPlace,
    PlaceMatchOption,
    PlaceMetadata,
    SimilarityComponents,
)
from app.shared.contracts.place import Coordinates


NOW = datetime(2026, 8, 11, tzinfo=UTC)


def context(
    *,
    avoids: list[str] | None = None,
    preferences: list[str] | None = None,
    children: int = 0,
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
        days=4,
        pace=TravelPace.balanced,
        capacity=CapacityRange(
            minimum_minutes=1440,
            typical_minutes=1920,
            maximum_minutes=2400,
        ),
        budget_mode=BudgetMode.relative_level,
        budget=BudgetInput(level="low", currency="VND", source="raw_prompt"),
        people=PeopleInput(adults=1, children=children, infants=0),
        preferences=preferences or [],
        avoids=avoids or [],
    )


def enriched_place(
    *,
    mandatory: bool = True,
    tags: list[str] | None = None,
    status: IdentityResolutionStatus = IdentityResolutionStatus.resolved,
    operational_status: OperationalStatus = OperationalStatus.active,
    opening_hours: list[str] | None = None,
    children_suitable: bool | None = True,
    cost_tier: CostTier = CostTier.low,
    fetched_at: datetime = NOW,
    destination_compatible: bool = True,
    coordinates: Coordinates | None = None,
) -> EnrichedIdentityPlace:
    place_id = "place_1"
    coordinates = coordinates or Coordinates(latitude=21.03, longitude=105.84)
    catalog = CatalogPlace(
        place_id=place_id,
        canonical_name="Example Place",
        adm_id="adm1_vn_ha_noi" if destination_compatible else None,
        country_code="VN" if destination_compatible else None,
        category="nightlife" if tags and "nightlife" in tags else "landmark",
        coordinates=coordinates,
        tags=tags or [],
    )
    option = PlaceMatchOption(
        place=catalog,
        method=SimilarityMethod.exact,
        components=SimilarityComponents(
            lexical_score=1,
            destination_score=1 if destination_compatible else 0,
            combined_score=0.95,
        ),
        rank=1,
        eligible_destination=destination_compatible,
    )
    metadata = PlaceMetadata(
        place_id=place_id,
        coordinates=coordinates,
        category=catalog.category,
        tags=tags or [],
        typical_duration_minutes=90,
        cost_tier=cost_tier,
        opening_hours=(opening_hours if opening_hours is not None else ["09:00-17:00"]),
        operational_status=operational_status,
        reservation_required=False,
        children_suitable=children_suitable,
        infants_suitable=True,
        source="knowledge_graph",
        fetched_at=fetched_at,
    )
    origin = EvidenceOrigin.input if mandatory else EvidenceOrigin.url
    return EnrichedIdentityPlace(
        place_id=place_id,
        canonical_name="Example Place",
        original_names=["Example Place"],
        source_tier=SourceTier.direct_user if mandatory else SourceTier.url,
        mandatory=mandatory,
        removable=not mandatory,
        status=status,
        identity_confidence=0.95,
        metadata=metadata,
        source_places=[
            SourcePlaceEvidence(
                origin=origin,
                evidence_type="raw_prompt",
                evidence="Visit Example Place",
            )
        ],
        match_options=[option],
    )


def test_complete_compatible_place_is_planner_ready() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(),
        context(),
    )

    assert result.state == PlaceLifecycleState.planner_ready
    assert result.planner_eligible is True
    assert result.findings == []


def test_provisional_input_is_conditional_and_planner_eligible() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(status=IdentityResolutionStatus.provisional),
        context(),
    )

    assert result.state == PlaceLifecycleState.conditional
    assert result.planner_eligible is True
    assert any(finding.code == "identity_provisional" for finding in result.findings)
    assert any(
        constraint.code == "verify_provisional_identity"
        for constraint in result.planner_constraints
    )


def test_optional_nightlife_is_rejected_by_soft_avoid() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(mandatory=False, tags=["nightlife"]),
        context(avoids=["nightlife"]),
    )

    assert result.state == PlaceLifecycleState.rejected
    assert result.planner_eligible is False
    assert result.avoid_conflicts == ["nightlife"]


def test_direct_user_nightlife_is_kept_with_warning() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(tags=["nightlife"]),
        context(avoids=["nightlife"]),
    )

    assert result.state == PlaceLifecycleState.conditional
    assert result.planner_eligible is True
    assert any(finding.code == "avoid_nightlife" for finding in result.findings)


def test_optional_url_alcohol_is_rejected_by_canonical_avoid() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(mandatory=False, tags=["item:Cocktail"]),
        context(avoids=["alcohol"]),
    )

    assert result.state == PlaceLifecycleState.rejected
    assert result.planner_eligible is False
    assert result.avoid_conflicts == ["alcohol"]


def test_direct_user_alcohol_is_kept_with_warning() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(tags=["cocktail"]),
        context(avoids=["alcohol"]),
    )

    assert result.state == PlaceLifecycleState.conditional
    assert result.planner_eligible is True
    assert result.avoid_conflicts == ["alcohol"]


def test_vietnamese_nightlife_and_drink_tags_match_english_avoids() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(
            mandatory=False,
            tags=[
                "experience:Trải nghiệm đồ uống buổi tối",
                "item:Cocktail",
            ],
        ),
        context(avoids=["nightlife", "alcohol"]),
    )

    assert result.state == PlaceLifecycleState.rejected
    assert result.planner_eligible is False
    assert result.avoid_conflicts == ["nightlife", "alcohol"]


def test_closed_direct_user_place_is_blocked_not_rejected() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(operational_status=OperationalStatus.permanently_closed),
        context(),
    )

    assert result.state == PlaceLifecycleState.blocked
    assert result.planner_eligible is False


def test_closed_optional_place_is_rejected() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(
            mandatory=False,
            operational_status=OperationalStatus.temporarily_closed,
        ),
        context(),
    )

    assert result.state == PlaceLifecycleState.rejected


def test_unknown_opening_hours_is_conditional_not_closed() -> None:
    place = enriched_place()
    place.metadata = place.metadata.model_copy(update={"opening_hours": None})

    result = PlaceEvaluationService(now=NOW).evaluate(place, context())

    assert result.state == PlaceLifecycleState.conditional
    assert all(finding.hard is False for finding in result.findings)
    assert any(
        constraint.code == "verify_opening_hours"
        for constraint in result.planner_constraints
    )


def test_child_unsuitable_optional_place_is_rejected() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(mandatory=False, children_suitable=False),
        context(children=1),
    )

    assert result.state == PlaceLifecycleState.rejected
    assert any(finding.code == "children_not_suitable" for finding in result.findings)


def test_low_budget_high_cost_is_soft_conditional() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(cost_tier=CostTier.high),
        context(),
    )

    assert result.state == PlaceLifecycleState.conditional
    assert any(finding.code == "relative_budget_conflict" for finding in result.findings)


def test_stale_metadata_requires_verification() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(fetched_at=NOW - timedelta(days=31)),
        context(),
    )

    assert result.state == PlaceLifecycleState.conditional
    assert result.data_quality.stale is True


def test_preference_match_is_reported() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(tags=["history"]),
        context(preferences=["history"]),
    )

    assert result.preference_matches == ["history"]


def test_destination_mismatch_rejects_optional_place() -> None:
    result = PlaceEvaluationService(now=NOW).evaluate(
        enriched_place(mandatory=False, destination_compatible=False),
        context(),
    )

    assert result.state == PlaceLifecycleState.rejected
    assert any(finding.code == "destination_mismatch" for finding in result.findings)


def test_batch_only_exposes_ready_or_conditional_ids() -> None:
    ready = enriched_place()
    rejected = enriched_place(
        mandatory=False,
        operational_status=OperationalStatus.permanently_closed,
    ).model_copy(update={"place_id": "place_2"})

    batch = PlaceEvaluationService(now=NOW).evaluate_all(
        [ready, rejected],
        context(),
    )

    assert batch.planner_eligible_place_ids == ["place_1"]
