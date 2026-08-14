from app.modules.place_checker.analysis_contract import AnalysisGap
from app.modules.place_checker.enums import GapType, IssueSeverity
from app.modules.place_checker.pool_policy import (
    per_gap_pool_target,
    pool_target_for_days,
)
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.tests.analysis_fixtures import analysis_context


def test_pool_target_is_eight_places_per_day_with_bounds() -> None:
    assert pool_target_for_days(1) == 10
    assert pool_target_for_days(4) == 32
    assert pool_target_for_days(7) == 56
    assert pool_target_for_days(10) == 60


def test_pool_target_is_shared_across_discovery_gaps() -> None:
    assert per_gap_pool_target(4, 4) == 8
    assert per_gap_pool_target(4, 2) == 12
    assert per_gap_pool_target(4, 1) == 12
    assert per_gap_pool_target(7, 8) == 7


def test_generic_travel_query_uses_trip_pool_target_without_changing_minimum() -> None:
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

    assert one_day.limit == 10
    assert three_days.limit == 24
