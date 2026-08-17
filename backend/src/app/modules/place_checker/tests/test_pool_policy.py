import asyncio

from app.modules.place_checker.analysis_contract import (
    AnalysisGap,
    CoverageAnalysis,
    GapAnalysis,
)
from app.modules.place_checker.enums import (
    CoverageLevel,
    GapType,
    IssueSeverity,
    RetrievalSourceKind,
)
from app.modules.place_checker.pool_policy import (
    activity_pool_target_for_days,
    combined_pool_target_for_days,
    entertainment_pool_target_for_days,
    food_pool_target_for_days,
    per_gap_pool_target,
    planner_pool_shortfall,
    pool_query_limit_for_days,
)
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context


def test_activity_pool_target_is_twenty_two_places_per_day() -> None:
    assert activity_pool_target_for_days(1) == 22
    assert activity_pool_target_for_days(4) == 88
    assert activity_pool_target_for_days(7) == 154
    assert activity_pool_target_for_days(30) == 420


def test_food_reserve_target_remains_separate() -> None:
    assert food_pool_target_for_days(1) == 16
    assert food_pool_target_for_days(3) == 48


def test_entertainment_reserve_target_is_six_per_day() -> None:
    assert entertainment_pool_target_for_days(1) == 6
    assert entertainment_pool_target_for_days(3) == 18


def test_combined_pool_has_independent_travel_and_restaurant_targets() -> None:
    assert combined_pool_target_for_days(1) == 49
    assert combined_pool_target_for_days(3) == 137
    assert combined_pool_target_for_days(5) == 225
    assert pool_query_limit_for_days(1) == 44
    assert pool_query_limit_for_days(3) == 60


def test_planner_pool_shortfall_is_a_hard_per_type_measurement() -> None:
    assert planner_pool_shortfall(days=1, travel_place_count=7, food_count=8) == (
        8,
        3,
        1,
        0,
    )
    assert planner_pool_shortfall(days=1, travel_place_count=8, food_count=10) == (
        8,
        3,
        0,
        0,
    )


def test_three_day_food_hard_minimum_tracks_nine_meal_slots() -> None:
    assert planner_pool_shortfall(days=3, travel_place_count=24, food_count=9) == (
        24,
        9,
        0,
        0,
    )
    assert planner_pool_shortfall(days=3, travel_place_count=24, food_count=8) == (
        24,
        9,
        0,
        1,
    )


def test_food_hard_minimum_also_requires_each_meal_type() -> None:
    assert planner_pool_shortfall(
        days=3,
        travel_place_count=24,
        food_count=9,
        food_meal_counts={"breakfast": 0, "lunch": 9, "dinner": 9},
    ) == (24, 9, 0, 3)


def test_pool_target_is_shared_across_discovery_gaps() -> None:
    assert per_gap_pool_target(4, 4) == 20
    assert per_gap_pool_target(4, 2) == 20
    assert per_gap_pool_target(4, 1) == 20
    assert per_gap_pool_target(7, 8) == 20


def test_generic_travel_query_uses_bounded_places_per_trip_day() -> None:
    gap = AnalysisGap(
        gap_id="gap:experience_coverage",
        gap_type=GapType.experience_coverage,
        severity=IssueSeverity.high,
        trigger="missing coverage",
        suggested_action="search",
    )

    one_day = TargetedRetrievalService._query(
        gap, analysis_context(days=1), None, anchor_place_ids=[], limit=3
    )
    three_days = TargetedRetrievalService._query(
        gap, analysis_context(days=3), None, anchor_place_ids=[], limit=6
    )

    assert one_day.limit == 22
    assert three_days.limit == 60


class RecordingSource:
    provider_name = "recording"
    source_kind = RetrievalSourceKind.knowledge_graph

    def __init__(self) -> None:
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return []


def test_core_pool_retrieval_leaves_restaurants_to_food_pool_service() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(source, ensure_core_pools=True)

    result = asyncio.run(service.retrieve(GapAnalysis(), analysis_context(days=3)))

    queries = {gap.gap_id: gap.query for gap in result.gaps}
    assert set(queries) == {
        "pool:travel_place_candidates",
        "pool:popular_landmark_candidates",
        "pool:accommodation_candidates",
        "pool:travel_place_reserve",
    }
    assert queries["pool:travel_place_candidates"].category_hint == "travel place"
    assert (
        queries["pool:popular_landmark_candidates"].query_text
        == "famous landmark must see top attraction"
    )
    assert queries["pool:accommodation_candidates"].category_hint == "accommodation"
    assert all(query.limit == 60 for query in queries.values())


def test_expanded_pool_queries_independent_activity_themes_and_styles() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(source, expand_pool=True)

    asyncio.run(service.retrieve(GapAnalysis(), analysis_context(days=3)))

    queries = {query.gap_id: query for query in source.queries}
    assert {
        "pool:culture_alternatives",
        "pool:nature_alternatives",
        "pool:shopping_alternatives",
        "pool:nightlife_alternatives",
        "pool:workshop_alternatives",
        "pool:performance_alternatives",
        "pool:outdoor_alternatives",
        "pool:family_alternatives",
        "pool:special_experience_alternatives",
        "pool:local_activity_alternatives",
    } <= set(queries)
    assert queries["pool:nature_alternatives"].relation_terms
    assert queries["pool:nightlife_alternatives"].relation_terms


def test_adaptive_pool_skips_reserve_queries_when_existing_pool_is_sufficient() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(
        source,
        ensure_core_pools=True,
        expand_pool=True,
    )
    coverage = CoverageAnalysis(
        level=CoverageLevel.sufficient,
        planner_eligible_place_count=85,
        mandatory_place_count=0,
        category_distribution={
            "landmark": 66,
            "entertainment": 18,
            "accommodation": 1,
        },
        resolved_item_count=0,
        unresolved_item_count=0,
        food_covered=False,
        experience_covered=True,
    )

    result = asyncio.run(
        service.retrieve(
            GapAnalysis(),
            analysis_context(days=3),
            coverage=coverage,
            excluded_gap_types={GapType.food_coverage},
        )
    )

    assert result.gaps == []
    assert source.queries == []


def test_adaptive_pool_only_adds_queries_needed_for_shortfall() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(
        source,
        ensure_core_pools=True,
        expand_pool=True,
    )
    coverage = CoverageAnalysis(
        level=CoverageLevel.partial,
        planner_eligible_place_count=31,
        mandatory_place_count=0,
        category_distribution={"landmark": 30, "accommodation": 1},
        resolved_item_count=0,
        unresolved_item_count=0,
        food_covered=False,
        experience_covered=True,
    )

    asyncio.run(
        service.retrieve(
            GapAnalysis(),
            analysis_context(days=3),
            coverage=coverage,
            excluded_gap_types={GapType.food_coverage},
        )
    )

    assert [query.gap_id for query in source.queries] == [
        "pool:travel_place_candidates",
        "pool:popular_landmark_candidates",
        "pool:culture_alternatives",
        "pool:nature_alternatives",
        "pool:shopping_alternatives",
        "pool:nightlife_alternatives",
        "pool:entertainment_alternatives",
    ]


def test_retrieval_can_skip_food_gaps_for_dedicated_food_pool() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(source)
    gaps = GapAnalysis(
        gaps=[
            AnalysisGap(
                gap_id="gap:food",
                gap_type=GapType.food_coverage,
                severity=IssueSeverity.high,
                trigger="missing food",
                suggested_action="search food",
            )
        ]
    )

    result = asyncio.run(
        service.retrieve(
            gaps,
            analysis_context(days=3),
            excluded_gap_types={GapType.food_coverage},
        )
    )

    assert result.gaps == []
    assert source.queries == []
