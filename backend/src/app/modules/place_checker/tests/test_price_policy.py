import pytest

from app.modules.place_checker.enums import CostTier
from app.modules.place_checker.evaluation.price_policy import (
    has_planner_cost,
    has_usable_cost,
    planner_cost,
    typical_cost,
)


@pytest.mark.parametrize(
    ("minimum", "typical", "maximum", "tier", "expected"),
    [
        (20_000, 999_999, 80_000, CostTier.low, 50_000),
        (None, 45_000, None, CostTier.low, 45_000),
        (30_000, None, None, CostTier.low, 30_000),
        (None, None, 70_000, CostTier.low, 70_000),
        (None, None, None, CostTier.free, 0),
        (None, None, None, CostTier.unknown, None),
    ],
)
def test_typical_cost_policy(minimum, typical, maximum, tier, expected) -> None:
    assert typical_cost(
        minimum=minimum,
        typical=typical,
        maximum=maximum,
        tier=tier,
    ) == expected


def test_missing_unknown_cost_is_not_usable() -> None:
    assert not has_usable_cost(
        minimum=None,
        typical=None,
        maximum=None,
        tier=CostTier.unknown,
    )


def test_unknown_general_place_cost_defaults_to_free_for_planner() -> None:
    assert planner_cost(
        category="travel_place",
        minimum=None,
        typical=None,
        maximum=None,
        tier=CostTier.unknown,
    ) == 0
    assert has_planner_cost(
        category="museum",
        minimum=None,
        typical=None,
        maximum=None,
        tier=CostTier.unknown,
    )


def test_unknown_venue_cost_remains_required_for_planner() -> None:
    assert planner_cost(
        category="restaurant",
        minimum=None,
        typical=None,
        maximum=None,
        tier=CostTier.unknown,
    ) is None
