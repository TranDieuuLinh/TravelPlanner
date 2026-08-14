import pytest

from app.shared.tools.daily_budget import DestinationDailyBudgetEstimator


@pytest.mark.parametrize(
    ("level", "daily_total"),
    [
        ("low", 750_852),
        ("medium", 1_377_807),
        ("high", 4_054_725),
    ],
)
def test_hanoi_daily_budget_matches_agreed_db_percentile_policy(
    level: str,
    daily_total: int,
) -> None:
    estimate = DestinationDailyBudgetEstimator().estimate(
        destination="Hà Nội",
        level=level,
        people=2,
        days=3,
    )

    assert estimate is not None
    assert estimate.daily_cost.total == daily_total
    assert estimate.nights == 2
    assert estimate.total_per_person == (
        daily_total * 3 - estimate.daily_cost.accommodation
    )
    assert estimate.daily_cost.currency == "VND"


def test_unknown_destination_does_not_reuse_hanoi_prices() -> None:
    estimate = DestinationDailyBudgetEstimator().estimate(
        destination="Paris",
        level="low",
        people=2,
        days=1,
    )

    assert estimate is None


def test_day_trip_budget_does_not_include_an_accommodation_night() -> None:
    estimate = DestinationDailyBudgetEstimator().estimate(
        destination="Hà Nội",
        level="low",
        people=2,
        days=1,
    )

    assert estimate is not None
    assert estimate.nights == 0
    assert estimate.total_per_person == (
        estimate.daily_cost.total - estimate.daily_cost.accommodation
    )
