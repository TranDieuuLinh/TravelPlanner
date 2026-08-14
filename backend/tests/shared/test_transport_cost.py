import pytest

from app.shared.tools.transport_cost import XanhSmTransportCostEstimator


def test_shared_hanoi_fare_returns_reusable_breakdown() -> None:
    estimate = XanhSmTransportCostEstimator().estimate_breakdown(
        4_200,
        "auto",
        people=2,
    )

    assert estimate.daytime_cost_per_person == 36_133
    assert estimate.late_night_surcharge_per_person == 10_000
    assert estimate.maximum_cost_per_person == 46_133
    assert estimate.vehicle_count == 1
    assert estimate.currency == "VND"
    assert estimate.market == "VN-HN"
    assert estimate.source_url.startswith("https://www.greensm.com/")
    assert estimate.verified_on == "2026-08-14"


def test_shared_transport_estimator_validates_inputs() -> None:
    estimator = XanhSmTransportCostEstimator()

    with pytest.raises(ValueError, match="negative"):
        estimator.estimate_breakdown(-1, "auto", people=1)
    with pytest.raises(ValueError, match="positive"):
        estimator.estimate_breakdown(1_000, "auto", people=0)
