import asyncio

from app.modules.place_checker.analysis_contract import AnalysisGap
from app.modules.place_checker.analysis_contract import GapAnalysis
from app.modules.place_checker.enums import (
    GapType,
    IssueSeverity,
    RetrievalSourceKind,
)
from app.modules.place_checker.pool_policy import (
    combined_pool_target_for_days,
    per_gap_pool_target,
    pool_query_limit_for_days,
    pool_target_for_days,
)
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context


def test_pool_target_is_twelve_places_per_day_with_bounds() -> None:
    assert pool_target_for_days(1) == 12
    assert pool_target_for_days(4) == 48
    assert pool_target_for_days(5) == 60
    assert pool_target_for_days(7) == 60
    assert pool_target_for_days(10) == 60


def test_combined_pool_has_independent_travel_and_restaurant_targets() -> None:
    assert combined_pool_target_for_days(1) == 24
    assert combined_pool_target_for_days(3) == 72
    assert combined_pool_target_for_days(5) == 120
    assert pool_query_limit_for_days(1) == 24
    assert pool_query_limit_for_days(3) == 60


def test_pool_target_is_shared_across_discovery_gaps() -> None:
    assert per_gap_pool_target(4, 4) == 12
    assert per_gap_pool_target(4, 2) == 12
    assert per_gap_pool_target(4, 1) == 12
    assert per_gap_pool_target(7, 8) == 8


def test_generic_travel_query_uses_twelve_places_per_trip_day() -> None:
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

    assert one_day.limit == 12
    assert three_days.limit == 36


class RecordingSource:
    provider_name = "recording"
    source_kind = RetrievalSourceKind.knowledge_graph

    def __init__(self) -> None:
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return []


def test_core_pool_retrieval_always_queries_both_entity_types() -> None:
    source = RecordingSource()
    service = TargetedRetrievalService(source, ensure_core_pools=True)

    result = asyncio.run(
        service.retrieve(GapAnalysis(), analysis_context(days=3))
    )

    queries = {gap.gap_id: gap.query for gap in result.gaps}
    assert set(queries) == {
        "pool:travel_place_candidates",
        "pool:restaurant_candidates",
        "pool:travel_place_reserve",
        "pool:restaurant_reserve",
    }
    assert queries["pool:travel_place_candidates"].category_hint == "travel place"
    assert queries["pool:restaurant_candidates"].category_hint == "restaurant"
    assert all(query.limit == 60 for query in queries.values())
