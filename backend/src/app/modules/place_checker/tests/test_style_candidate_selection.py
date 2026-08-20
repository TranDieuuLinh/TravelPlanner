import asyncio
import inspect

from app.modules.place_checker.adapters.postgres_style_candidate_query import (
    STYLE_CANDIDATE_SQL,
    STYLE_INTENT_RESOLUTION_SQL,
)
from app.modules.place_checker.enums import CostTier, OperationalStatus
from app.modules.place_checker.resolution.item_contract import ItemResolutionBatch
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.resolution.contract import PlaceMetadata
from app.modules.place_checker.resolution.contract import (
    EvidenceEnrichmentOutput,
    IdentityResolutionBatch,
)
from app.modules.place_checker.selection.style_contract import (
    ResolvedStyleIntent,
    StyleCandidate,
    StyleCandidateSourceBatch,
)
from app.modules.place_checker.selection.style_service import (
    StyleCandidateSelectionService,
)
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.shared.contracts.place import Coordinates


class FakeStyleSource:
    def __init__(self, batch: StyleCandidateSourceBatch) -> None:
        self.batch = batch
        self.calls = []

    async def find_style_candidates(self, **kwargs):
        self.calls.append(kwargs)
        return self.batch


class FakeContextBuilder:
    async def build(self, payload):
        return analysis_context(days=payload.days)


class EmptyIdentityResolution:
    async def resolve_all(self, places, context):
        return IdentityResolutionBatch()


class EmptyEvidenceEnrichment:
    async def merge_and_enrich(self, identities, notes):
        return EvidenceEnrichmentOutput()


class EmptyItemResolution:
    async def resolve_all(self, items, context, related_places):
        return ItemResolutionBatch()


def intent(
    style_id: str,
    style_name: str,
    *,
    source: str = "style",
    input_value: str | None = None,
    item_id: str | None = None,
    item_name: str | None = None,
) -> ResolvedStyleIntent:
    return ResolvedStyleIntent(
        input_value=input_value or style_name,
        source=source,
        style_id=style_id,
        style_name=style_name,
        item_id=item_id,
        item_name=item_name,
    )


def candidate(
    place_id: str,
    style_id: str,
    *,
    style_name: str = "Văn hóa",
    item_id: str | None = None,
    item_name: str | None = None,
    relationship_source: str = "Has_Style",
    tags: list[str] | None = None,
    rating: float = 4.5,
) -> StyleCandidate:
    entity_type = "TravelPlace"
    return StyleCandidate(
        place_id=place_id,
        place_name=f"Place {place_id}",
        entity_type=entity_type,
        style_id=style_id,
        style_name=style_name,
        item_id=item_id,
        item_name=item_name,
        relationship_source=relationship_source,
        metadata=PlaceMetadata(
            place_id=place_id,
            coordinates=Coordinates(latitude=21.03, longitude=105.84),
            category="travel_place",
            tags=tags or ["văn hóa"],
            rating=rating,
            review_count=100,
            typical_duration_minutes=90,
            cost_tier=CostTier.low,
            cost_currency="VND",
            typical_cost=50_000,
            opening_hours=["08:00-18:00"],
            operational_status=OperationalStatus.active,
        ),
    )


def test_applies_two_per_day_to_each_resolved_active_style() -> None:
    intents = [
        intent("style_culture", "Văn hóa"),
        intent("style_outdoor", "Ngoài trời"),
    ]
    candidates = [
        *[candidate(f"culture:{index}", "style_culture") for index in range(5)],
        *[
            candidate(
                f"outdoor:{index}",
                "style_outdoor",
                style_name="Ngoài trời",
                tags=["thiên nhiên"],
            )
            for index in range(5)
        ],
    ]
    source = FakeStyleSource(
        StyleCandidateSourceBatch(resolved_intents=intents, candidates=candidates)
    )

    result = asyncio.run(
        StyleCandidateSelectionService(source).select(
            analysis_context(days=2),
            style_inputs=["style:Văn hóa", "Ngoài trời"],
            item_inputs=[],
        )
    )

    assert len(result.selections) == 8
    assert all(item.target_candidates == 4 for item in result.coverage)
    assert all(item.selected_candidates == 4 for item in result.coverage)
    assert all(item.complete for item in result.coverage)
    assert source.calls[0]["style_inputs"] == ["van hoa", "ngoai troi"]


def test_requested_canonical_item_is_filled_before_unrequested_items() -> None:
    breakfast = intent(
        "style_breakfast",
        "Ăn sáng",
        source="item",
        input_value="pho",
        item_id="food_pho",
        item_name="Phở",
    )
    candidates = [
        candidate(
            "restaurant:bun",
            "style_breakfast",
            style_name="Ăn sáng",
            item_id="food_bun",
            item_name="Bún",
            relationship_source="Offer_Item",
            rating=5,
        ),
        candidate(
            "restaurant:pho:1",
            "style_breakfast",
            style_name="Ăn sáng",
            item_id="food_pho",
            item_name="Phở",
            relationship_source="Offer_Item",
        ),
        candidate(
            "restaurant:pho:2",
            "style_breakfast",
            style_name="Ăn sáng",
            item_id="food_pho",
            item_name="Phở",
            relationship_source="Offer_Item",
        ),
    ]
    source = FakeStyleSource(
        StyleCandidateSourceBatch(
            resolved_intents=[breakfast],
            candidates=candidates,
        )
    )

    result = asyncio.run(
        StyleCandidateSelectionService(source).select(
            analysis_context(days=1),
            style_inputs=[],
            item_inputs=["Phở"],
        )
    )

    assert [item.item_id for item in result.selections] == ["food_pho", "food_pho"]
    assert all(item.relationship_source == "Offer_Item" for item in result.selections)


def test_request_local_tag_counts_prefer_the_less_used_tag() -> None:
    source = FakeStyleSource(
        StyleCandidateSourceBatch(
            resolved_intents=[intent("style_culture", "Văn hóa")],
            candidates=[
                candidate(
                    "culture:1",
                    "style_culture",
                    tags=["văn hóa"],
                    rating=5,
                ),
                candidate(
                    "culture:2",
                    "style_culture",
                    tags=["văn hóa"],
                    rating=4.9,
                ),
                candidate(
                    "nature:1",
                    "style_culture",
                    tags=["thiên nhiên"],
                    rating=4,
                ),
            ],
        )
    )

    result = asyncio.run(
        StyleCandidateSelectionService(source).select(
            analysis_context(days=1),
            style_inputs=["Văn hóa"],
            item_inputs=[],
        )
    )

    assert [item.place_id for item in result.selections] == [
        "culture:1",
        "nature:1",
    ]


def test_deduplicates_place_globally_and_reports_per_style_shortfall() -> None:
    intents = [
        intent("style_a", "Style A"),
        intent("style_b", "Style B"),
    ]
    candidates = [
        candidate("shared", "style_a", style_name="Style A"),
        candidate("a-only", "style_a", style_name="Style A"),
        candidate("shared", "style_b", style_name="Style B"),
    ]
    source = FakeStyleSource(
        StyleCandidateSourceBatch(resolved_intents=intents, candidates=candidates)
    )

    result = asyncio.run(
        StyleCandidateSelectionService(source).select(
            analysis_context(days=1),
            style_inputs=["Style A", "Style B"],
            item_inputs=[],
        )
    )

    assert len({item.place_id for item in result.selections}) == len(result.selections)
    incomplete = [item for item in result.coverage if not item.complete]
    assert {item.style_id for item in incomplete} == {"style_a", "style_b"}
    assert all(
        item.shortfall_reason == "catalog_has_insufficient_eligible_unique_places"
        for item in incomplete
    )
    assert "Style candidate coverage còn thiếu" in result.warnings[-1]


def test_returns_unresolved_inputs_without_fabricating_candidates() -> None:
    source = FakeStyleSource(
        StyleCandidateSourceBatch(
            unresolved_style_inputs=["khong co style"],
            unresolved_item_inputs=["khong co item"],
        )
    )

    result = asyncio.run(
        StyleCandidateSelectionService(source).select(
            analysis_context(),
            style_inputs=["style:Không có Style"],
            item_inputs=["Không có Item"],
        )
    )

    assert result.selections == []
    assert result.coverage == []
    assert result.unresolved_style_inputs == ["khong co style"]
    assert result.unresolved_item_inputs == ["khong co item"]


def test_postgres_queries_use_canonical_ids_and_both_relationship_paths() -> None:
    assert "item.entity_type IN" in STYLE_INTENT_RESOLUTION_SQL
    assert "alias.normalized_alias" in STYLE_INTENT_RESOLUTION_SQL
    assert "item.item_id" in STYLE_INTENT_RESOLUTION_SQL
    assert "offered.to_entity_id = item.item_id" in STYLE_CANDIDATE_SQL
    assert "offered.relationship_type = 'Offer_Item'" in STYLE_CANDIDATE_SQL
    assert "styled.relationship_type = 'Has_Style'" in STYLE_CANDIDATE_SQL
    assert "holder.entity_type IN ('TravelPlace', 'Restaurant', 'DrinkDessert')" in (
        STYLE_CANDIDATE_SQL
    )
    assert "NOT EXISTS" in STYLE_CANDIDATE_SQL
    assert "normalized_name =" not in STYLE_CANDIDATE_SQL


def test_pipeline_does_not_expose_has_style_discovery() -> None:
    assert (
        "style_selection"
        not in inspect.signature(PlaceCheckerPipeline.__init__).parameters
    )
