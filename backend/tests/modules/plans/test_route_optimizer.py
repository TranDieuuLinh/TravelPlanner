from datetime import datetime, time, timezone

from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.routing.local_time import (
    combine_routing_datetime,
    routing_today,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.provider import (
    RouteCalculation,
    TravelTimeMatrix,
)


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


def test_route_optimizer_preserves_url_itinerary_order_when_requested() -> None:
    items = [
        _item("Far east", "09:00-10:00", 21.03, 105.90),
        _item("Near west", "10:30-11:30", 21.03, 105.81),
        _item("Middle", "13:00-14:00", 21.03, 105.85),
    ]

    optimized, legs = GeographicRouteOptimizer().optimize(
        items,
        preserve_order=True,
    )

    assert [item.name for item in optimized] == [
        "Far east",
        "Near west",
        "Middle",
    ]
    assert [(leg.from_place, leg.to_place) for leg in legs] == [
        ("Far east", "Near west"),
        ("Near west", "Middle"),
    ]


def test_route_optimizer_uses_valhalla_walking_route_for_short_leg() -> None:
    provider = FakeRouteProvider(walking_distance=900)
    optimizer = GeographicRouteOptimizer(provider)

    _, legs = optimizer.optimize(
        [
            _item("A", "09:00-10:00", 21.0300, 105.8500),
            _item("B", "10:30-11:30", 21.0310, 105.8510),
        ],
        preserve_order=True,
    )

    assert provider.requested_modes == ["pedestrian", "car"]
    assert legs[0].mode == "walk"
    assert legs[0].distance_meters == 900
    assert legs[0].estimated_duration_minutes == 11
    assert legs[0].source == "valhalla_routing"
    assert legs[0].verified is True
    assert legs[0].fetched_at is not None
    assert [option.mode for option in legs[0].alternatives] == [
        "ride_hailing"
    ]


def test_route_optimizer_uses_valhalla_car_route_when_walk_is_too_long() -> None:
    provider = FakeRouteProvider(walking_distance=1800)
    optimizer = GeographicRouteOptimizer(provider)

    _, legs = optimizer.optimize(
        [
            _item("A", "09:00-10:00", 21.0300, 105.8500),
            _item("B", "10:30-11:30", 21.0500, 105.8700),
        ],
        preserve_order=True,
    )

    assert provider.requested_modes == ["pedestrian", "car"]
    assert legs[0].mode == "ride_hailing"
    assert legs[0].distance_meters == 1600
    assert legs[0].estimated_duration_minutes == 4
    assert legs[0].source == "valhalla_routing"
    assert legs[0].verified is True
    assert [option.mode for option in legs[0].alternatives] == ["walk"]


def test_calculate_leg_forces_walking_even_when_route_is_long() -> None:
    provider = FakeRouteProvider(walking_distance=2800)
    optimizer = GeographicRouteOptimizer(provider)

    leg = optimizer.calculate_leg(
        _item("A", "09:00-10:00", 21.0300, 105.8500),
        _item("B", "10:30-11:30", 21.0500, 105.8700),
        requested_mode="walk",
    )

    assert provider.requested_modes == ["pedestrian"]
    assert leg.mode == "walk"
    assert leg.distance_meters == 2800


def test_navigation_order_minimizes_complete_path_from_user_location() -> None:
    optimizer = GeographicRouteOptimizer()
    items = [
        _item("North east", "09:00-10:00", 2.0, 2.0),
        _item("South", "10:30-11:30", 0.0, 1.0),
        _item("North west", "13:00-14:00", 2.0, 0.0),
    ]

    ordered = optimizer.order_from_start(items, start=(0.0, 0.0))

    assert [item.name for item in ordered] == [
        "South",
        "North east",
        "North west",
    ]


def test_navigation_order_prefers_provider_time_over_geo_distance() -> None:
    matrix = FakeMatrixProvider(
        [
            [0, 100, 20, 90],
            [100, 0, 10, 80],
            [20, 70, 0, 10],
            [90, 10, 80, 0],
        ]
    )
    optimizer = GeographicRouteOptimizer(matrix_provider=matrix)
    items = [
        _item("Nearest geographically", "09:00-10:00", 0.0, 0.01),
        _item("Fast first", "10:30-11:30", 1.0, 1.0),
        _item("Last", "13:00-14:00", 2.0, 2.0),
    ]

    ordered = optimizer.order_from_start(items, start=(0.0, 0.0))

    assert [item.name for item in ordered] == [
        "Fast first",
        "Last",
        "Nearest geographically",
    ]
    assert matrix.requested_modes == ["car"]


def test_route_optimizer_exposes_transit_as_alternative_for_dated_trip() -> None:
    provider = FakeRouteProvider(walking_distance=1800)
    transit = FakeTransitRouteProvider()
    optimizer = GeographicRouteOptimizer(
        provider,
        transit,
        transit_enabled=True,
    )

    _, legs = optimizer.optimize(
        [
            _item("A", "09:00-10:00", 21.0300, 105.8500),
            _item("B", "10:30-11:30", 21.0500, 105.8700),
        ],
        preserve_order=True,
        trip_start_date="2026-08-01",
    )

    assert legs[0].mode == "ride_hailing"
    assert [option.mode for option in legs[0].alternatives] == [
        "walk",
        "public_transit",
    ]
    assert legs[0].alternatives[1].details["lines"] == ["31"]
    assert transit.departure_times[0].isoformat() == (
        "2026-08-01T10:00:00+07:00"
    )


def test_route_optimizer_exposes_current_transit_for_undated_trip() -> None:
    provider = FakeRouteProvider(walking_distance=1800)
    transit = FakeTransitRouteProvider()
    optimizer = GeographicRouteOptimizer(
        provider,
        transit,
        transit_enabled=True,
    )

    _, legs = optimizer.optimize(
        [
            _item("A", "09:00-10:00", 21.0300, 105.8500),
            _item("B", "10:30-11:30", 21.0500, 105.8700),
        ],
        preserve_order=True,
    )

    assert [option.mode for option in legs[0].alternatives] == [
        "walk",
        "public_transit",
    ]
    assert transit.departure_times == [
        combine_routing_datetime(routing_today(), time(10, 0))
    ]


def test_route_optimizer_selects_transit_when_user_prefers_bus() -> None:
    provider = FakeRouteProvider(walking_distance=1800)
    transit = FakeTransitRouteProvider()
    optimizer = GeographicRouteOptimizer(
        provider,
        transit,
        transit_enabled=True,
    )

    _, legs = optimizer.optimize(
        [
            _item("A", "09:00-10:00", 21.0300, 105.8500),
            _item("B", "10:30-11:30", 21.0500, 105.8700),
        ],
        preserve_order=True,
        trip_start_date="2026-08-01",
        preferred_modes={"bus"},
    )

    assert legs[0].mode == "public_transit"
    assert legs[0].source == "opentripplanner_transit"
    assert legs[0].details["transitModes"] == ["bus"]
    assert [option.mode for option in legs[0].alternatives] == [
        "walk",
        "ride_hailing",
    ]


class FakeRouteProvider:
    def __init__(self, *, walking_distance: int) -> None:
        self.walking_distance = walking_distance
        self.requested_modes: list[str] = []

    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        transport_mode: str,
        departure_time: datetime | None = None,
    ) -> RouteCalculation:
        del departure_time
        self.requested_modes.append(transport_mode)
        if transport_mode == "pedestrian":
            distance = self.walking_distance
            duration = 601
        else:
            distance = 1600
            duration = 181
        return RouteCalculation(
            distance_meters=distance,
            duration_seconds=duration,
            geometry_coordinates=[origin, destination],
            provider="valhalla_routing",
            fetched_at=datetime.now(timezone.utc),
        )


class FakeTransitRouteProvider:
    def __init__(self) -> None:
        self.departure_times: list[datetime | None] = []

    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        departure_time: datetime | None,
        modes: tuple[str, ...] = (),
    ) -> RouteCalculation:
        self.departure_times.append(departure_time)
        return RouteCalculation(
            distance_meters=2800,
            duration_seconds=900,
            geometry_coordinates=[origin, destination],
            provider="opentripplanner_transit",
            fetched_at=datetime.now(timezone.utc),
            details={"transitModes": ["bus"], "lines": ["31"]},
        )


class FakeMatrixProvider:
    def __init__(self, travel_times: list[list[int | None]]) -> None:
        self.travel_times = travel_times
        self.requested_modes: list[str] = []

    def calculate(
        self,
        coordinates: list[tuple[float, float]],
        *,
        transport_mode: str,
        departure_time: datetime | None,
    ) -> TravelTimeMatrix:
        del coordinates, departure_time
        self.requested_modes.append(transport_mode)
        return TravelTimeMatrix(
            travel_times_seconds=self.travel_times,
            provider="fake_matrix",
            fetched_at=datetime.now(timezone.utc),
        )


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
