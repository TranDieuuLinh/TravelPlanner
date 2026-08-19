from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.modules.itinerary_planner.directions import DirectionsService
from app.modules.itinerary_planner.routing_models import RouteDetail


class FakeRouteProvider:
    async def route(self, legs, profile):
        return tuple(
            RouteDetail(
                origin_node_id=leg.origin.node_id,
                destination_node_id=leg.destination.node_id,
                duration_seconds=300,
                distance_meters=2500,
                encoded_polyline=None,
                provider="valhalla",
            )
            for leg in legs
        )


def build_client() -> TestClient:
    app = create_app(Settings(database_url=""))
    app.router.lifespan_context = None
    app.state.directions_service = DirectionsService(FakeRouteProvider())
    return TestClient(app)


def test_day_directions_returns_camel_case_route_legs() -> None:
    response = build_client().post(
        "/v1/plans/day-directions",
        json={
            "origin": {"latitude": 21.0, "longitude": 105.8, "name": "Origin"},
            "destinations": [
                {
                    "itemId": "place-1",
                    "name": "First place",
                    "latitude": 21.01,
                    "longitude": 105.81,
                },
                {
                    "itemId": "place-2",
                    "name": "Second place",
                    "latitude": 21.02,
                    "longitude": 105.82,
                },
            ],
            "requestedMode": "walk",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["mode"] == "walk"
    assert payload[0]["toItemId"] == "place-1"
    assert payload[1]["toItemId"] == "place-2"
    assert payload[0]["geometryCoordinates"] == [[21.0, 105.8], [21.01, 105.81]]


def test_current_location_route_is_available() -> None:
    response = build_client().post(
        "/v1/plans/current-location-route",
        json={
            "origin": {"latitude": 21.0, "longitude": 105.8},
            "destination": {
                "itemId": "place-1",
                "name": "First place",
                "latitude": 21.01,
                "longitude": 105.81,
            },
            "preferredModes": ["walk"],
        },
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "walk"
