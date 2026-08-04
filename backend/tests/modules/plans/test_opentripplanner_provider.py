from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytest

from app.integrations.routing.opentripplanner import (
    OpenTripPlannerTransitProvider,
)


def test_otp_returns_scheduled_bus_itinerary_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []
    walk_shape = _encode_polyline(
        [(10.7769, 106.7009), (10.7775, 106.7000)]
    )
    bus_shape = _encode_polyline(
        [(10.7775, 106.7000), (10.7798, 106.6990)]
    )
    final_walk_shape = _encode_polyline(
        [(10.7798, 106.6990), (10.7802, 106.6987)]
    )

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> httpx.Response:
            del headers
            request = httpx.Request("POST", url, json=json)
            requests.append(json)
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": {
                        "plan": {
                            "itineraries": [
                                {
                                    "duration": 780,
                                    "legs": [
                                        {
                                            "mode": "WALK",
                                            "transitLeg": False,
                                            "distance": 120,
                                            "duration": 120,
                                            "from": {"name": "Điểm A"},
                                            "to": {"name": "Trạm đầu"},
                                            "legGeometry": {
                                                "points": walk_shape
                                            },
                                            "route": None,
                                            "agency": None,
                                        },
                                        {
                                            "mode": "BUS",
                                            "transitLeg": True,
                                            "distance": 3100,
                                            "duration": 600,
                                            "headsign": "Bến Thành",
                                            "realTime": True,
                                            "from": {"name": "Trạm đầu"},
                                            "to": {"name": "Trạm cuối"},
                                            "legGeometry": {
                                                "points": bus_shape
                                            },
                                            "route": {
                                                "shortName": "31",
                                                "longName": "Tuyến 31",
                                            },
                                            "agency": {"name": "Buýt TP.HCM"},
                                        },
                                        {
                                            "mode": "WALK",
                                            "transitLeg": False,
                                            "distance": 80,
                                            "duration": 60,
                                            "from": {"name": "Trạm cuối"},
                                            "to": {"name": "Điểm B"},
                                            "legGeometry": {
                                                "points": final_walk_shape
                                            },
                                            "route": None,
                                            "agency": None,
                                        },
                                    ],
                                }
                            ]
                        }
                    }
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.opentripplanner.httpx.Client",
        FakeClient,
    )
    provider = OpenTripPlannerTransitProvider(
        base_url="http://opentripplanner:8080/otp/gtfs/v1",
    )

    result = provider.calculate(
        (10.7769, 106.7009),
        (10.7802, 106.6987),
        departure_time=datetime(2026, 8, 1, 9, 0),
        modes=("bus",),
    )

    assert result is not None
    assert result.provider == "opentripplanner_transit"
    assert result.distance_meters == 3300
    assert result.duration_seconds == 780
    assert result.details == {
        "transitModes": ["bus"],
        "lines": ["31"],
        "agencies": ["Buýt TP.HCM"],
        "realTime": True,
        "scheduleStatus": "current",
        "segments": [
            {
                "mode": "walk",
                "fromPlace": "Điểm A",
                "toPlace": "Trạm đầu",
                "distanceMeters": 120,
                "estimatedDurationMinutes": 2,
                "geometryCoordinates": [
                    (10.7769, 106.7009),
                    (10.7775, 106.7),
                ],
                "line": None,
                "headsign": None,
            },
            {
                "mode": "bus",
                "fromPlace": "Trạm đầu",
                "toPlace": "Trạm cuối",
                "distanceMeters": 3100,
                "estimatedDurationMinutes": 10,
                "geometryCoordinates": [
                    (10.7775, 106.7),
                    (10.7798, 106.699),
                ],
                "line": "31",
                "headsign": "Bến Thành",
            },
            {
                "mode": "walk",
                "fromPlace": "Trạm cuối",
                "toPlace": "Điểm B",
                "distanceMeters": 80,
                "estimatedDurationMinutes": 1,
                "geometryCoordinates": [
                    (10.7798, 106.699),
                    (10.7802, 106.6987),
                ],
                "line": None,
                "headsign": None,
            },
        ],
    }
    assert len(result.geometry_coordinates) == 4
    variables = requests[0]["variables"]
    assert variables["date"] == "2026-08-01"
    assert variables["time"] == "09:00:00"
    assert "apiKey" not in requests[0]


def test_otp_requires_departure_time_for_schedule_routing() -> None:
    provider = OpenTripPlannerTransitProvider(
        base_url="http://opentripplanner:8080/otp/gtfs/v1",
    )


def test_otp_normalizes_utc_departure_to_hanoi_service_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(
            self,
            url: str,
            *,
            json: dict[str, Any],
            **_: Any,
        ) -> httpx.Response:
            requests.append(json)
            request = httpx.Request("POST", url, json=json)
            return httpx.Response(
                200,
                request=request,
                json={"data": {"plan": {"itineraries": []}}},
            )

    monkeypatch.setattr(
        "app.integrations.routing.opentripplanner.httpx.Client",
        FakeClient,
    )
    provider = OpenTripPlannerTransitProvider(
        base_url="http://opentripplanner:8080/otp/gtfs/v1",
    )

    provider.calculate(
        (10.7769, 106.7009),
        (10.7798, 106.6990),
        departure_time=datetime.fromisoformat("2026-07-31T17:15:00+00:00"),
    )

    variables = requests[0]["variables"]
    assert variables["date"] == "2026-08-01"
    assert variables["time"] == "00:15:00"

    assert (
        provider.calculate(
            (10.7769, 106.7009),
            (10.7798, 106.6990),
            departure_time=None,
        )
        is None
    )


def test_otp_rejects_walk_only_itinerary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, url: str, **_: Any) -> httpx.Response:
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                request=request,
                json={
                    "data": {
                        "plan": {
                            "itineraries": [
                                {
                                    "duration": 600,
                                    "legs": [
                                        {
                                            "mode": "WALK",
                                            "transitLeg": False,
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.opentripplanner.httpx.Client",
        FakeClient,
    )
    provider = OpenTripPlannerTransitProvider(
        base_url="http://opentripplanner:8080/otp/gtfs/v1",
    )

    assert (
        provider.calculate(
            (10.7769, 106.7009),
            (10.7798, 106.6990),
            departure_time=datetime(2026, 8, 1, 9, 0),
        )
        is None
    )


def _encode_polyline(
    coordinates: list[tuple[float, float]],
) -> str:
    factor = 10**5
    previous_latitude = 0
    previous_longitude = 0
    output: list[str] = []
    for latitude, longitude in coordinates:
        encoded_latitude = round(latitude * factor)
        encoded_longitude = round(longitude * factor)
        output.extend(_encode_value(encoded_latitude - previous_latitude))
        output.extend(_encode_value(encoded_longitude - previous_longitude))
        previous_latitude = encoded_latitude
        previous_longitude = encoded_longitude
    return "".join(output)


def _encode_value(value: int) -> list[str]:
    unsigned = ~(value << 1) if value < 0 else value << 1
    output: list[str] = []
    while unsigned >= 0x20:
        output.append(chr((0x20 | (unsigned & 0x1F)) + 63))
        unsigned >>= 5
    output.append(chr(unsigned + 63))
    return output
