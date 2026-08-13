from app.modules.place_checker.pool_policy import (
    per_gap_pool_target,
    pool_target_for_days,
)


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
