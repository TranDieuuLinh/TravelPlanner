import pytest

from app.shared.tools.daily_cost import DailyCostCalculator


def test_daily_cost_composes_independent_per_person_components() -> None:
    estimate = DailyCostCalculator.estimate(
        accommodation=500_000,
        food=450_000,
        local_transport=150_000,
        activities=250_000,
        misc=100_000,
        currency="vnd",
    )

    assert estimate.total == 1_450_000
    assert estimate.currency == "VND"


def test_daily_cost_rejects_negative_component() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        DailyCostCalculator.estimate(food=-1)
