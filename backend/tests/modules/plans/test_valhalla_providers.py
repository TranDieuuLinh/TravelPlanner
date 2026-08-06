from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from app.integrations.routing.valhalla import ValhallaRouteProvider
from app.integrations.routing.valhalla_matrix import (
    ValhallaTravelTimeMatrixProvider,
)
from app.integrations.routing.opentripplanner import (
    OpenTripPlannerTransitProvider,
)
from app.modules.plans import dependencies


def test_valhalla_route_parses_summary_shape_and_uses_no_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[httpx.Request, dict[str, Any]]] = []
    shape = _encode_polyline(
        [(10.7769, 106.7009), (10.7798, 106.6990)],
        precision=6,
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
            json: dict[str, Any],
        ) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            requests.append((request, json))
            return httpx.Response(
                200,
                request=request,
                json={
                    "trip": {
                        "summary": {"length": 1.281, "time": 174},
                        "legs": [{"shape": shape}],
                    }
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.valhalla.httpx.Client",
        FakeClient,
    )
    provider = ValhallaRouteProvider(
        base_url="http://valhalla:8002",
    )

    result = provider.calculate(
        (10.7769, 106.7009),
        (10.7798, 106.6990),
        transport_mode="pedestrian",
        departure_time=datetime(
            2026,
            8,
            1,
            9,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert result is not None
    assert result.distance_meters == 1281
    assert result.duration_seconds == 174
    assert result.provider == "valhalla_routing"
    assert result.geometry_coordinates == pytest.approx(
        [(10.7769, 106.7009), (10.7798, 106.6990)]
    )
    assert requests[0][0].url.path == "/route"
    assert "apiKey" not in requests[0][1]
    assert requests[0][1]["costing"] == "pedestrian"
    assert requests[0][1]["date_time"] == {
        "type": 1,
        "value": "2026-08-01T09:00",
    }


def test_valhalla_route_batches_an_ordered_day_into_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []
    first_shape = _encode_polyline(
        [(21.0300, 105.8500), (21.0310, 105.8510)],
        precision=6,
    )
    second_shape = _encode_polyline(
        [(21.0310, 105.8510), (21.0500, 105.8700)],
        precision=6,
    )

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def post(self, url: str, *, json: dict[str, Any]) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            requests.append(json)
            return httpx.Response(
                200,
                request=request,
                json={
                    "trip": {
                        "summary": {"length": 2.5, "time": 600},
                        "legs": [
                            {
                                "summary": {"length": 0.9, "time": 180},
                                "shape": first_shape,
                            },
                            {
                                "summary": {"length": 1.6, "time": 420},
                                "shape": second_shape,
                            },
                        ],
                    }
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.valhalla.httpx.Client",
        FakeClient,
    )
    provider = ValhallaRouteProvider(base_url="http://valhalla:8002")

    routes = provider.calculate_many(
        [
            (21.0300, 105.8500),
            (21.0310, 105.8510),
            (21.0500, 105.8700),
        ],
        transport_mode="car",
    )

    assert routes is not None
    assert [route.distance_meters for route in routes] == [900, 1600]
    assert [route.duration_seconds for route in routes] == [180, 420]
    assert len(requests) == 1
    assert len(requests[0]["locations"]) == 3
    assert requests[0]["costing"] == "auto"


def test_valhalla_matrix_parses_unreachable_pairs_without_key(
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
        ) -> httpx.Response:
            request = httpx.Request("POST", url, json=json)
            requests.append(json)
            return httpx.Response(
                200,
                request=request,
                json={
                    "sources_to_targets": {
                        "durations": [[0, None], [60.4, 0]],
                        "distances": [[0, None], [1.2, 0]],
                    }
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.valhalla_matrix.httpx.Client",
        FakeClient,
    )
    provider = ValhallaTravelTimeMatrixProvider(
        base_url="http://valhalla:8002",
    )

    result = provider.calculate(
        [(21.0, 105.8), (21.1, 105.9)],
        transport_mode="car",
        departure_time=datetime(
            2026,
            8,
            1,
            9,
            0,
            tzinfo=timezone.utc,
        ),
    )

    assert result is not None
    assert result.travel_times_seconds == [[0, None], [60, 0]]
    assert result.distances_meters == [[0, None], [1200, 0]]
    assert result.provider == "valhalla_matrix"
    assert requests[0]["costing"] == "auto"
    assert requests[0]["verbose"] is False
    assert requests[0]["units"] == "kilometers"
    assert requests[0]["date_time"] == {
        "type": 3,
        "value": "2026-08-01T09:00",
    }
    assert all("apiKey" not in location for location in requests[0]["sources"])


def test_runtime_wires_valhalla_and_otp_without_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "route_provider",
        "valhalla",
    )

    optimizer = dependencies._get_route_optimizer()

    assert isinstance(optimizer.route_provider, ValhallaRouteProvider)
    assert isinstance(
        optimizer.matrix_provider,
        ValhallaTravelTimeMatrixProvider,
    )
    assert isinstance(
        optimizer.transit_provider,
        OpenTripPlannerTransitProvider,
    )


def _encode_polyline(
    coordinates: list[tuple[float, float]],
    *,
    precision: int,
) -> str:
    factor = 10**precision
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
