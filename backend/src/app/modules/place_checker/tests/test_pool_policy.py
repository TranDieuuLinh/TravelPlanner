from app.modules.place_checker.pool_policy import (
    per_gap_pool_target,
    pool_target_for_days,
)


def test_pool_target_is_fifteen_places_per_day_with_bounds() -> None:
    assert pool_target_for_days(1) == 20
    assert pool_target_for_days(4) == 60
    assert pool_target_for_days(7) == 105
    assert pool_target_for_days(10) == 120


def test_pool_target_is_shared_across_discovery_gaps() -> None:
    assert per_gap_pool_target(4, 4) == 15
    assert per_gap_pool_target(4, 2) == 30
    assert per_gap_pool_target(4, 1) == 50
    assert per_gap_pool_target(7, 8) == 14
