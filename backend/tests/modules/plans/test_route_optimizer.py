from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


def test_route_optimizer_reorders_slots_and_builds_unverified_legs() -> None:
    items = [
        _item("Far east", "09:00-10:00", 21.03, 105.90),
        _item("Near west", "10:30-11:30", 21.03, 105.81),
        _item("Middle", "13:00-14:00", 21.03, 105.85),
    ]

    optimized, legs = GeographicRouteOptimizer().optimize(items)

    assert [item.time_window for item in optimized] == [
        "09:00-10:00",
        "10:30-11:30",
        "13:00-14:00",
    ]
    assert [item.name for item in optimized] in [
        ["Far east", "Middle", "Near west"],
        ["Near west", "Middle", "Far east"],
    ]
    assert len(legs) == 2
    assert all(leg.source == "geodesic_estimate" for leg in legs)
    assert all(leg.verified is False for leg in legs)
    assert all(leg.estimated_duration_minutes > 0 for leg in legs)


def _item(
    name: str,
    time_window: str,
    latitude: float,
    longitude: float,
) -> PlanItem:
    return PlanItem(
        itemId=name,
        name=name,
        timeWindow=time_window,
        placeType="attraction",
        latitude=latitude,
        longitude=longitude,
    )
