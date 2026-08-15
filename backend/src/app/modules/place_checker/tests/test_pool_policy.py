import asyncio

from app.modules.place_checker.analysis_contract import AnalysisGap
from app.modules.place_checker.analysis_contract import GapAnalysis
from app.modules.place_checker.enums import (
    GapType,
    IssueSeverity,
    RetrievalSourceKind,
)
from app.modules.place_checker.pool_policy import (
    activity_pool_target_for_days,
    combined_pool_target_for_days,
    food_pool_target_for_days,
    per_gap_pool_target,
    planner_pool_shortfall,
    pool_query_limit_for_days,
)
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context


def test_activity_pool_target_is_fourteen_places_per_day() -> None:
    assert activity_pool_target_for_days(1) == 14
    assert activity_pool_target_for_days(4) == 56
    assert activity_pool_target_for_days(7) == 98
    assert activity_pool_target_for_days(30) == 420


def test_food_reserve_target_remains_separate() -> None:
    assert food_pool_target_for_days(1) == 10
    assert food_pool_target_for_days(3) == 30


def test_combined_pool_has_independent_travel_and_restaurant_targets() -> None:
    assert combined_pool_target_for_days(1) == 29
    assert combined_pool_target_for_days(3) == 77
    assert combined_pool_target_for_days(5) == 125
    assert pool_query_limit_for_days(1) == 28
    assert pool_query_limit_for_days(3) == 60


def test_planner_pool_shortfall_is_a_hard_per_type_measurement() -> None:
    assert planner_pool_shortfall(days=1, travel_place_count=13, food_count=8) == (
        14,
        3,
        1,
        0,
    )
    assert planner_pool_shortfall(days=1, travel_place_count=14, food_count=10) == (
        14,
        3,
        0,
        0,
    )


def test_three_day_food_hard_minimum_tracks_nine_meal_slots() -> None:
    assert planner_pool_shortfall(days=3, travel_place_count=42, food_count=9) == (
        42,
        9,
        0,
        0,
    )
    assert planner_pool_shortfall(days=3, travel_place_count=42, food_count=8) == (
        42,
        9,
        0,
        1,
    )


def test_food_hard_minimum_also_requires_each_meal_type() -> None:
    assert planner_pool_shortfall(
        days=3,
        travel_place_count=42,
        food_count=9,
        food_meal_counts={"breakfast": 0, "lunch": 9, "dinner": 9},
    ) == (42, 9, 0, 3)


def test_pool_target_is_shared_across_discovery_gaps() -> None:
    assert per_gap_pool_target(4, 4) == 14
    assert per_gap_pool_target(4, 2) == 20
    assert per_gap_pool_target(4, 1) == 20
    assert per_gap_pool_target(7, 8) == 13


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

    assert one_day.limit == 14
    assert three_days.limit == 42


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
        "pool:accommodation_candidates",
        "pool:travel_place_reserve",
    }
    assert queries["pool:travel_place_candidates"].category_hint == "travel place"
    assert queries["pool:accommodation_candidates"].category_hint == "accommodation"
    assert all(query.limit == 60 for query in queries.values())


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
