import asyncio

from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    BudgetInput,
    CapacityRange,
    InputItem,
    PeopleInput,
    TravelPace,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import (
    BudgetMode,
    CostTier,
    IdentityResolutionStatus,
    ItemResolutionStatus,
    SourceTier,
)
from app.modules.place_checker.item_resolution import InputItemResolutionService
from app.modules.place_checker.resolution_contract import (
    EnrichedIdentityPlace,
    PlaceMetadata,
)
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import (
    PlaceProviderCandidate,
    PlaceSearchProviderTimeout,
    SearchPlacesTool,
)
from app.shared.tools.search_places.adapters import InMemoryPlaceSearch
from app.shared.tools.search_places.policy import PlaceSearchPolicy

HANOI_ADM_ID = "adm1_vn_ha_noi"


class FakeMetadataRepository:
    def __init__(self, metadata: dict[str, PlaceMetadata]) -> None:
        self.metadata = metadata

    async def get_many(self, place_ids: list[str]) -> dict[str, PlaceMetadata]:
        return {
            place_id: self.metadata[place_id]
            for place_id in place_ids
            if place_id in self.metadata
        }


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
            adm_id=HANOI_ADM_ID,
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
        budget=BudgetInput(
            level="low",
            currency="VND",
            source="raw_prompt",
        ),
        people=PeopleInput(adults=1, children=children, infants=0),
        preferences=preferences or [],
        avoids=avoids or [],
    )


def item(
    name: str = "pho",
    *,
    item_type: str = "food",
    action: str = "eat",
    related_place_name: str | None = None,
) -> InputItem:
    return InputItem(
        name=name,
        item_type=item_type,
        action=action,
        related_place_name=related_place_name,
        evidence=f"{action} {name}",
        confidence=0.97,
    )


def venue(
    place_id: str,
    name: str,
    *,
    category: str = "restaurant",
    tags: list[str] | None = None,
    confidence: float = 0.95,
    latitude: float = 21.03,
    longitude: float = 105.84,
) -> PlaceProviderCandidate:
    return PlaceProviderCandidate(
        provider="knowledge_graph",
        entity_id=place_id,
        name=name,
        adm_ids=[HANOI_ADM_ID],
        adm_names=["Hà Nội"],
        canonical_type=category,
        tags=tags or [],
        address="Hanoi",
        coordinates=Coordinates(latitude=latitude, longitude=longitude),
        data_confidence=confidence,
    )


def resolver(
    candidates: list[PlaceProviderCandidate],
    *,
    external: InMemoryPlaceSearch | None = None,
) -> tuple[InputItemResolutionService, InMemoryPlaceSearch]:
    kg = InMemoryPlaceSearch(candidates, provider_name="knowledge_graph")
    metadata = FakeMetadataRepository(
        {
            candidate.entity_id: PlaceMetadata(
                place_id=candidate.entity_id,
                category=candidate.canonical_type,
                coordinates=candidate.coordinates,
                cost_tier=CostTier.low,
                cost_currency="VND",
                minimum_cost=30_000,
                typical_cost=50_000,
                maximum_cost=70_000,
                typical_duration_minutes=60,
            )
            for candidate in candidates
            if candidate.entity_id
        }
    )
    return InputItemResolutionService(
        SearchPlacesTool(kg, external), metadata_repository=metadata
    ), kg


def checked_place(
    place_id: str,
    name: str,
    *,
    category: str,
    latitude: float = 21.03,
    longitude: float = 105.84,
) -> EnrichedIdentityPlace:
    return EnrichedIdentityPlace(
        place_id=place_id,
        canonical_name=name,
        original_names=[name],
        source_tier=SourceTier.direct_user,
        mandatory=True,
        removable=False,
        status=IdentityResolutionStatus.resolved,
        identity_confidence=0.98,
        metadata=PlaceMetadata(
            place_id=place_id,
            category=category,
            coordinates=Coordinates(latitude=latitude, longitude=longitude),
            cost_tier=CostTier.low,
            cost_currency="VND",
            minimum_cost=30_000,
            typical_cost=50_000,
            maximum_cost=70_000,
        ),
    )


def test_pho_resolves_to_real_venue_with_alternative() -> None:
    service, kg = resolver(
        [
            venue("pho_1", "Phở Bát Đàn", tags=["pho"], confidence=0.99),
            venue("pho_2", "Phở Thìn", tags=["pho"], confidence=0.90),
        ]
    )

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.status == ItemResolutionStatus.resolved
    assert result.selected.place_id == "pho_1"
    assert [place.place_id for place in result.alternatives] == ["pho_2"]
    assert result.confidence > 0.8
    assert result.selected.name != result.item.name
    assert kg.calls == [["pho"]]


def test_unresolved_item_does_not_create_synthetic_place() -> None:
    service, _ = resolver([])

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.status == ItemResolutionStatus.unresolved
    assert result.selected is None
    assert result.alternatives == []
    assert result.normalized_requirement == "pho"


def test_weak_but_eligible_venue_is_only_partially_resolved() -> None:
    service, _ = resolver(
        [venue("weak_1", "Unrelated Venue", tags=[], confidence=0.5)]
    )

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.status == ItemResolutionStatus.partially_resolved
    assert result.selected is None
    assert result.alternatives[0].place_id == "weak_1"


def test_ambiguous_item_type_can_use_requirement_tags() -> None:
    service, _ = resolver(
        [
            venue(
                "workshop_1",
                "Hanoi Art Space",
                category="creative_space",
                tags=["art workshop"],
            )
        ]
    )

    result = asyncio.run(
        service.resolve_all(
            [item("art workshop", item_type="other", action="join")],
            context(),
        )
    ).items[0]

    assert result.status == ItemResolutionStatus.resolved
    assert result.selected.place_id == "workshop_1"


def test_activity_creates_special_experience_with_canonical_anchor() -> None:
    service, _ = resolver(
        [
            venue(
                "lake_1",
                "Hoàn Kiếm Lake",
                category="travel_place",
                tags=["walk around lake"],
            )
        ]
    )

    result = asyncio.run(
        service.resolve_all(
            [item("walk around lake", item_type="activity", action="walk")],
            context(),
        )
    ).items[0]

    assert result.status == ItemResolutionStatus.resolved
    assert result.special_experience.anchor_place_id == "lake_1"
    assert result.special_experience.action == "walk"


def test_soft_avoid_filters_item_venue_with_explicit_tag() -> None:
    service, _ = resolver(
        [
            venue(
                "club_1",
                "Night Club",
                category="nightlife",
                tags=["nightlife"],
            )
        ]
    )

    result = asyncio.run(
        service.resolve_all(
            [item("nightlife", item_type="activity", action="visit")],
            context(avoids=["nightlife"]),
        )
    ).items[0]

    assert result.status == ItemResolutionStatus.unresolved
    assert result.selected is None


def test_canonical_alcohol_avoid_filters_cocktail_item_venue() -> None:
    service, _ = resolver(
        [venue("cocktail_1", "Cocktail Bar", tags=["item:Cocktail"])]
    )

    result = asyncio.run(
        service.resolve_all(
            [item("cocktail", item_type="drink", action="drink")],
            context(avoids=["alcohol"]),
        )
    ).items[0]

    assert result.status == ItemResolutionStatus.unresolved
    assert result.selected is None


def test_metadata_reranks_low_cost_venue_for_low_budget() -> None:
    high_cost = venue("pho_high", "Premium Pho", tags=["pho"], confidence=0.99)
    low_cost = venue("pho_low", "Local Pho", tags=["pho"], confidence=0.90)
    kg = InMemoryPlaceSearch([high_cost, low_cost], provider_name="knowledge_graph")
    metadata = FakeMetadataRepository(
        {
            "pho_high": PlaceMetadata(
                place_id="pho_high",
                cost_tier=CostTier.premium,
                typical_cost=800_000,
            ),
            "pho_low": PlaceMetadata(
                place_id="pho_low", cost_tier=CostTier.low, typical_cost=50_000
            ),
        }
    )
    service = InputItemResolutionService(
        SearchPlacesTool(kg),
        metadata_repository=metadata,
    )

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.selected.place_id == "pho_low"
    assert result.selected.cost_tier == CostTier.low
    assert result.selection_reason == "context_and_proximity_reranked_requirement_match"


def test_item_resolution_skips_higher_scored_venue_without_price() -> None:
    unknown = venue("pho_unknown", "Unknown Price Pho", tags=["pho"], confidence=0.99)
    priced = venue("pho_priced", "Priced Pho", tags=["pho"], confidence=0.90)
    kg = InMemoryPlaceSearch([unknown, priced], provider_name="knowledge_graph")
    metadata = FakeMetadataRepository(
        {
            "pho_unknown": PlaceMetadata(place_id="pho_unknown"),
            "pho_priced": PlaceMetadata(
                place_id="pho_priced",
                cost_tier=CostTier.low,
                typical_cost=50_000,
            ),
        }
    )
    service = InputItemResolutionService(
        SearchPlacesTool(kg),
        metadata_repository=metadata,
        policy=PlaceSearchPolicy(requirement_acceptance_score=0.5),
    )

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.selected.place_id == "pho_priced"
    assert result.selected.typical_cost == 50_000


def test_related_food_place_is_reused_without_another_search() -> None:
    service, kg = resolver([])
    restaurant = checked_place(
        "pho_bat_dan",
        "Phở Gia Truyền Bát Đàn",
        category="restaurant",
    )

    result = asyncio.run(
        service.resolve_all(
            [
                item(
                    "phở",
                    related_place_name="Phở Gia Truyền Bát Đàn",
                )
            ],
            context(),
            [restaurant],
        )
    ).items[0]

    assert result.status == ItemResolutionStatus.resolved
    assert result.selected.place_id == "pho_bat_dan"
    assert result.selected.anchor_distance_km == 0
    assert result.selection_reason == "related_place_direct_match"
    assert kg.calls == []


def test_food_search_prefers_venue_near_related_attraction() -> None:
    service, _ = resolver(
        [
            venue(
                "pho_far",
                "Phở Far",
                tags=["pho"],
                confidence=0.99,
                latitude=21.09,
            ),
            venue(
                "pho_near",
                "Phở Near",
                tags=["pho"],
                confidence=0.90,
                latitude=21.032,
            ),
        ]
    )
    attraction = checked_place(
        "west_lake",
        "Hồ Tây",
        category="travel_place",
        latitude=21.03,
    )

    result = asyncio.run(
        service.resolve_all(
            [item("pho", related_place_name="Hồ Tây")],
            context(),
            [attraction],
        )
    ).items[0]

    assert result.selected.place_id == "pho_near"
    assert result.selected.proximity_status == "nearby"
    assert result.selected.anchor_distance_km < 2
    assert all(option.place_id != "pho_far" for option in result.alternatives)


def test_proximity_is_recomputed_from_metadata_repository_coordinates() -> None:
    candidate = venue("pho_db", "Phở Database", tags=["pho"]).model_copy(
        update={"coordinates": None}
    )
    kg = InMemoryPlaceSearch([candidate], provider_name="knowledge_graph")
    metadata = FakeMetadataRepository(
        {
            "pho_db": PlaceMetadata(
                place_id="pho_db",
                category="restaurant",
                coordinates=Coordinates(latitude=21.031, longitude=105.84),
                cost_tier=CostTier.low,
                typical_cost=50_000,
            )
        }
    )
    service = InputItemResolutionService(
        SearchPlacesTool(kg),
        metadata_repository=metadata,
    )
    attraction = checked_place(
        "west_lake",
        "Hồ Tây",
        category="travel_place",
        latitude=21.03,
    )

    result = asyncio.run(
        service.resolve_all(
            [item("pho", related_place_name="Hồ Tây")],
            context(),
            [attraction],
        )
    ).items[0]

    assert result.selected.place_id == "pho_db"
    assert result.selected.anchor_distance_km < 2
    assert result.selected.proximity_status == "nearby"


def test_metadata_filters_child_unsuitable_venue() -> None:
    unsuitable = venue("pho_adult", "Adult Pho", tags=["pho"], confidence=0.99)
    suitable = venue("pho_family", "Family Pho", tags=["pho"], confidence=0.90)
    kg = InMemoryPlaceSearch([unsuitable, suitable], provider_name="knowledge_graph")
    metadata = FakeMetadataRepository(
        {
            "pho_adult": PlaceMetadata(
                place_id="pho_adult",
                children_suitable=False,
                cost_tier=CostTier.low,
                typical_cost=50_000,
            ),
            "pho_family": PlaceMetadata(
                place_id="pho_family",
                children_suitable=True,
                cost_tier=CostTier.low,
                typical_cost=50_000,
            ),
        }
    )
    service = InputItemResolutionService(
        SearchPlacesTool(kg),
        metadata_repository=metadata,
    )

    result = asyncio.run(
        service.resolve_all([item()], context(children=1))
    ).items[0]

    assert result.selected.place_id == "pho_family"


def test_checkpoint_three_never_calls_external_fallback() -> None:
    external = InMemoryPlaceSearch(
        [venue("external_pho", "External Pho", tags=["pho"])],
        provider_name="external",
    )
    service, _ = resolver([], external=external)

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.status == ItemResolutionStatus.unresolved
    assert external.calls == []


def test_provider_timeout_preserves_item_and_attempt() -> None:
    kg = InMemoryPlaceSearch(
        provider_name="knowledge_graph",
        error=PlaceSearchProviderTimeout("database timed out"),
    )
    service = InputItemResolutionService(SearchPlacesTool(kg))

    result = asyncio.run(service.resolve_all([item()], context())).items[0]

    assert result.status == ItemResolutionStatus.unresolved
    assert result.item.name == "pho"
    assert result.selection_reason == "knowledge_graph_provider_error"
    assert result.provider_attempts[0].outcome == "timeout"
