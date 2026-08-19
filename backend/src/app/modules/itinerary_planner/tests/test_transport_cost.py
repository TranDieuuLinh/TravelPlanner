import pytest

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)


def test_hanoi_tiered_fare_adds_buffer_and_splits_per_person() -> None:
    estimator = XanhSmTransportCostEstimator()

    daytime, night_surcharge = estimator.estimate(4_200, "auto", people=2)

    # Published vehicle fare: 30,500 + 2.2 * 14,700 = 62,840.
    # Planning fare adds 15%, then one shared car is split between two people.
    assert daytime == 36_133
    assert night_surcharge == 10_000


def test_uses_multiple_cars_when_group_exceeds_capacity() -> None:
    estimator = XanhSmTransportCostEstimator()

    daytime, night_surcharge = estimator.estimate(4_200, "auto", people=5)

    assert daytime == 28_907
    assert night_surcharge == 8_000


def test_zero_distance_costs_zero_and_non_auto_is_rejected() -> None:
    estimator = XanhSmTransportCostEstimator()

    assert estimator.estimate(0, "auto", people=2) == (0, 0)
    with pytest.raises(ValueError, match="auto profile"):
        estimator.estimate(1_000, "pedestrian", people=2)
