from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import app
from app.modules.plans.dependencies import (
    get_current_location_route_service,
)
from app.modules.plans.routing.current_location_service import (
    CurrentLocationRouteService,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.provider import RouteCalculation


def test_current_location_route_returns_only_road_choices(
    client: TestClient,
) -> None:
    road = FakeRoadProvider()
    transit = FakeTransitProvider()
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(road, transit)
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/current-location-route",
        json={
            "origin": {
                "latitude": 10.7769,
                "longitude": 106.7009,
            },
            "destination": {
                "itemId": "stop-1",
                "name": "Bưu điện Thành phố",
                "address": "2 Công xã Paris",
                "latitude": 10.7798,
                "longitude": 106.6990,
            },
            "departureTime": "2026-07-30T09:00:00+07:00",
            "preferredModes": [],
            "avoidModes": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["fromItemId"] == "current-location"
    assert body["toItemId"] == "stop-1"
    assert body["fromPlace"] == "Vị trí của bạn"
    assert body["mode"] == "walk"
    assert body["source"] == "valhalla_routing"
    assert body["verified"] is True
    assert body["geometryCoordinates"][0] == [10.7769, 106.7009]
    assert [choice["mode"] for choice in body["alternatives"]] == [
        "ride_hailing",
    ]
    assert transit.departure_times == []


def test_current_location_route_rejects_invalid_coordinates(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/plans/current-location-route",
        json={
            "origin": {"latitude": 91, "longitude": 106.7},
            "destination": {
                "name": "Điểm đến",
                "latitude": 10.7,
                "longitude": 106.8,
            },
        },
    )

    assert response.status_code == 422


def test_day_directions_forces_car_through_every_stop(
    client: TestClient,
) -> None:
    road = FakeRoadProvider()
    service = CurrentLocationRouteService(GeographicRouteOptimizer(road))
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "itemId": "stop-1",
                    "name": "Điểm 1",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
                {
                    "itemId": "stop-2",
                    "name": "Điểm 2",
                    "latitude": 10.7820,
                    "longitude": 106.6950,
                },
            ],
            "requestedMode": "car",
            "departureTime": "2026-07-31T09:00:00+07:00",
        },
    )

    assert response.status_code == 200
    legs = response.json()
    assert [leg["fromPlace"] for leg in legs] == [
        "Vị trí của bạn",
        "Điểm 1",
    ]
    assert [leg["toPlace"] for leg in legs] == ["Điểm 1", "Điểm 2"]
    assert all(leg["mode"] == "car" for leg in legs)
    assert road.requested_modes == ["car", "car"]


def test_day_directions_rejects_empty_destination_list(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [],
            "requestedMode": "walk",
        },
    )

    assert response.status_code == 422


def test_day_directions_ignores_bus_and_uses_road_routes(
    client: TestClient,
) -> None:
    transit = FakeTransitProvider()
    road = FakeRoadProvider()
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(road, transit)
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "name": "Điểm 1",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
                {
                    "name": "Điểm 2",
                    "latitude": 10.7820,
                    "longitude": 106.6950,
                },
            ],
            "requestedMode": "bus",
            "departureTime": "2026-07-31T09:00:00+07:00",
        },
    )

    assert response.status_code == 200
    assert [leg["mode"] for leg in response.json()] == ["walk", "walk"]
    assert road.requested_modes == ["pedestrian", "car"] * 2
    assert transit.departure_times == []


def test_day_directions_returns_recommended_routes_with_per_leg_choices(
    client: TestClient,
) -> None:
    road = FakeRoadProvider()
    transit = FakeTransitProvider()
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(road, transit)
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "name": "Điểm 1",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
                {
                    "name": "Điểm 2",
                    "latitude": 10.7820,
                    "longitude": 106.6950,
                },
            ],
            "departureTime": "2026-07-31T09:00:00+07:00",
        },
    )

    assert response.status_code == 200
    legs = response.json()
    assert [leg["mode"] for leg in legs] == ["walk", "walk"]
    assert [
        {option["mode"] for option in leg["alternatives"]}
        for leg in legs
    ] == [{"ride_hailing"}, {"ride_hailing"}]
    assert transit.departure_times == []


def test_day_directions_does_not_request_transit_for_later_legs(
    client: TestClient,
) -> None:
    transit = FakeTransitProvider()
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(FakeRoadProvider(), transit)
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "name": "Tràng Tiền Plaza",
                    "timeWindow": "08:00-10:00",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
                {
                    "name": "90 Đường Tàu",
                    "timeWindow": "12:00-13:00",
                    "latitude": 10.7820,
                    "longitude": 106.6950,
                },
            ],
            "departureTime": "2026-08-01T00:15:00+07:00",
        },
    )

    assert response.status_code == 200
    assert transit.departure_times == []


def test_day_directions_bus_request_does_not_call_transit(
    client: TestClient,
) -> None:
    transit = FakeTransitProvider()
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(transit_provider=transit)
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "name": "Tràng Tiền Plaza",
                    "timeWindow": "08:00-10:00",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
                {
                    "name": "90 Đường Tàu",
                    "timeWindow": "12:00-13:00",
                    "latitude": 10.7820,
                    "longitude": 106.6950,
                },
            ],
            "requestedMode": "bus",
            "departureTime": "2026-07-31T17:15:00Z",
        },
    )

    assert response.status_code == 200
    assert transit.departure_times == []
    assert all(leg["mode"] == "walk" for leg in response.json())


def test_day_directions_omits_transit_choice_when_provider_has_no_route(
    client: TestClient,
) -> None:
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(
            FakeRoadProvider(),
            UnavailableTransitProvider(),
        )
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "name": "Điểm 1",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
            ],
            "departureTime": "2026-07-31T09:00:00+07:00",
        },
    )

    assert response.status_code == 200
    leg = response.json()[0]
    assert leg["mode"] == "walk"
    assert {option["mode"] for option in leg["alternatives"]} == {
        "ride_hailing"
    }
    assert all(
        option["source"] != "geodesic_estimate"
        for option in leg["alternatives"]
    )


def test_day_directions_forced_bus_falls_back_without_calling_transit(
    client: TestClient,
) -> None:
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(
            transit_provider=UnavailableTransitProvider()
        )
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.7769, "longitude": 106.7009},
            "destinations": [
                {
                    "name": "Điểm 1",
                    "latitude": 10.7798,
                    "longitude": 106.6990,
                },
            ],
            "requestedMode": "bus",
            "departureTime": "2026-07-31T09:00:00+07:00",
        },
    )

    assert response.status_code == 200
    assert response.json()[0]["mode"] == "walk"
    assert response.json()[0]["source"] == "geodesic_estimate"


def test_day_directions_preserves_itinerary_stop_order(
    client: TestClient,
) -> None:
    service = CurrentLocationRouteService(
        GeographicRouteOptimizer(
            matrix_provider=UnexpectedMatrixProvider(),
        )
    )
    app.dependency_overrides[get_current_location_route_service] = (
        lambda: service
    )

    response = client.post(
        "/api/plans/day-directions",
        json={
            "origin": {"latitude": 10.0, "longitude": 106.0},
            "destinations": [
                {
                    "name": "Xa",
                    "latitude": 10.0,
                    "longitude": 106.3,
                },
                {
                    "name": "Gần",
                    "latitude": 10.0,
                    "longitude": 106.1,
                },
                {
                    "name": "Giữa",
                    "latitude": 10.0,
                    "longitude": 106.2,
                },
            ],
            "departureTime": "2026-07-31T09:00:00+07:00",
        },
    )

    assert response.status_code == 200
    assert [leg["toPlace"] for leg in response.json()] == [
        "Xa",
        "Gần",
        "Giữa",
    ]


class FakeRoadProvider:
    def __init__(self) -> None:
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
        return RouteCalculation(
            distance_meters=700 if transport_mode == "pedestrian" else 900,
            duration_seconds=540,
            geometry_coordinates=[origin, destination],
            provider="valhalla_routing",
            fetched_at=datetime.now(timezone.utc),
        )


class FakeTransitProvider:
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
            distance_meters=1200,
            duration_seconds=720,
            geometry_coordinates=[origin, destination],
            provider="opentripplanner_transit",
            fetched_at=datetime.now(timezone.utc),
            details={
                "transitModes": ["bus"],
                "lines": ["01"],
                "segments": [
                    {
                        "mode": "walk",
                        "fromPlace": "OTP origin",
                        "toPlace": "Trạm A",
                        "distanceMeters": 100,
                        "estimatedDurationMinutes": 2,
                        "geometryCoordinates": [origin, origin],
                    },
                    {
                        "mode": "bus",
                        "fromPlace": "Trạm A",
                        "toPlace": "Trạm B",
                        "distanceMeters": 900,
                        "estimatedDurationMinutes": 8,
                        "geometryCoordinates": [origin, destination],
                        "line": "01",
                    },
                    {
                        "mode": "walk",
                        "fromPlace": "Trạm B",
                        "toPlace": "OTP destination",
                        "distanceMeters": 200,
                        "estimatedDurationMinutes": 2,
                        "geometryCoordinates": [destination, destination],
                    },
                ],
            },
        )


class UnavailableTransitProvider:
    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        departure_time: datetime | None,
        modes: tuple[str, ...] = (),
    ) -> None:
        del origin, destination, departure_time, modes
        return None


class UnexpectedMatrixProvider:
    def calculate(
        self,
        coordinates: list[tuple[float, float]],
        *,
        transport_mode: str,
        departure_time: datetime | None,
    ) -> None:
        del coordinates, transport_mode, departure_time
        raise AssertionError(
            "Day directions must not compare or reorder itinerary stops"
        )
