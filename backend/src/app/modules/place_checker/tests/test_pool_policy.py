import asyncio

from app.modules.place_checker.analysis.contract import CoverageAnalysis, GapAnalysis
from app.modules.place_checker.enums import CoverageLevel, GapType, RetrievalSourceKind
from app.modules.place_checker.selection.pool_policy import (
    activity_pool_target_for_days,
    combined_pool_target_for_days,
    drink_dessert_pool_target_for_days,
    entertainment_pool_target_for_days,
    food_pool_target_for_days,
    per_gap_pool_target,
    planner_pool_shortfall,
    pool_query_limit_for_days,
)
from app.modules.place_checker.retrieval.service import TargetedRetrievalService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context


def test_independent_pool_targets() -> None:
    assert activity_pool_target_for_days(1) == 12
    assert activity_pool_target_for_days(3) == 36
    assert food_pool_target_for_days(1) == 6
    assert food_pool_target_for_days(3) == 18
    assert entertainment_pool_target_for_days(1) == 2
    assert entertainment_pool_target_for_days(3) == 6
    assert drink_dessert_pool_target_for_days(1) == 3
    assert drink_dessert_pool_target_for_days(3) == 9


def test_combined_target_counts_every_pool_once() -> None:
    assert combined_pool_target_for_days(1) == 26
    assert combined_pool_target_for_days(3) == 72
    assert pool_query_limit_for_days(1) == 24
    assert pool_query_limit_for_days(3) == 60


def test_planner_shortfall_uses_activity_and_six_food_per_day() -> None:
    assert planner_pool_shortfall(days=1, travel_place_count=7, food_count=8) == (
        12,
        6,
        5,
        0,
    )
    assert planner_pool_shortfall(days=3, travel_place_count=36, food_count=18) == (
        36,
        18,
        0,
        0,
    )


def test_food_shortfall_also_checks_breakfast_lunch_and_dinner() -> None:
    assert planner_pool_shortfall(
        days=3,
        travel_place_count=36,
        food_count=18,
        food_meal_counts={"breakfast": 0, "lunch": 18, "dinner": 18},
    ) == (36, 18, 0, 3)


def test_per_gap_limit_remains_bounded() -> None:
    assert per_gap_pool_target(4, 4) == 12
    assert per_gap_pool_target(4, 2) == 20
    assert per_gap_pool_target(4, 1) == 20


class RecordingSource:
    provider_name = "recording"
    source_kind = RetrievalSourceKind.knowledge_graph

    def __init__(self) -> None:
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return []


def test_runtime_creates_exactly_one_query_per_pool() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(
        source,
        ensure_core_pools=True,
        expand_pool=True,
    )

    result = asyncio.run(service.retrieve(GapAnalysis(), analysis_context(days=3)))

    queries = {gap.gap_id: gap.query for gap in result.gaps}
    assert set(queries) == {
        "pool:travel_place_candidates",
        "pool:restaurant_candidates",
        "pool:drink_dessert_candidates",
        "pool:entertainment_candidates",
        "pool:accommodation_candidates",
    }
    assert queries["pool:travel_place_candidates"].limit == 60
    assert queries["pool:restaurant_candidates"].limit == 18
    assert queries["pool:drink_dessert_candidates"].limit == 9
    assert queries["pool:entertainment_candidates"].limit == 8
    assert all(not query.relation_terms for query in queries.values())


def test_sufficient_existing_counts_skip_all_pool_queries() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(
        source,
        ensure_core_pools=True,
        expand_pool=True,
    )
    coverage = CoverageAnalysis(
        level=CoverageLevel.sufficient,
        planner_eligible_place_count=72,
        mandatory_place_count=0,
        category_distribution={
            "travel_place": 36,
            "restaurant": 18,
            "drink_dessert": 9,
            "entertainment": 6,
            "accommodation": 3,
        },
        resolved_item_count=0,
        unresolved_item_count=0,
        food_covered=True,
        experience_covered=True,
    )

    result = asyncio.run(
        service.retrieve(GapAnalysis(), analysis_context(days=3), coverage=coverage)
    )

    assert result.gaps == []
    assert source.queries == []


def test_excluded_gap_type_is_respected_outside_runtime_configuration() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(source)

    result = asyncio.run(
        service.retrieve(
            GapAnalysis(),
            analysis_context(days=3),
            excluded_gap_types={GapType.food_coverage},
        )
    )

    assert result.gaps == []
