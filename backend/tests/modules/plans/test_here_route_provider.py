from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.integrations.routing.here import (
    HereRouteProvider,
    decode_flexible_polyline,
)


EXAMPLE_POLYLINE = "BFoz5xJ67i1B1B7PzIhaxL7Y"


def test_decode_flexible_polyline_returns_here_geometry() -> None:
    assert decode_flexible_polyline(EXAMPLE_POLYLINE) == pytest.approx(
        [
            (50.10228, 8.69821),
            (50.10201, 8.69567),
            (50.10063, 8.69150),
            (50.09878, 8.68752),
        ]
    )


def test_here_route_provider_parses_summary_geometry_and_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def get(self, url: str, *, params: dict[str, str]) -> httpx.Response:
            request = httpx.Request("GET", url, params=params)
            requests.append(request)
            return httpx.Response(
                200,
                request=request,
                json={
                    "routes": [
                        {
                            "sections": [
                                {
                                    "summary": {
                                        "length": 1281,
                                        "duration": 174,
                                    },
                                    "polyline": EXAMPLE_POLYLINE,
                                }
                            ]
                        }
                    ]
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.here.httpx.Client",
        FakeClient,
    )
    provider = HereRouteProvider(
        base_url="https://router.example.test",
        api_key="secret-key",
        min_interval_seconds=0,
    )

    result = provider.calculate(
        (21.0, 105.8),
        (21.1, 105.9),
        transport_mode="pedestrian",
    )

    assert result is not None
    assert result.distance_meters == 1281
    assert result.duration_seconds == 174
    assert result.provider == "here_routing_v8"
    assert result.geometry_coordinates[0] == pytest.approx(
        (50.10228, 8.69821)
    )
    assert len(requests) == 1
    params = requests[0].url.params
    assert params["transportMode"] == "pedestrian"
    assert params["routingMode"] == "fast"
    assert params["departureTime"] == "any"

    cached = provider.calculate(
        (21.0, 105.8),
        (21.1, 105.9),
        transport_mode="pedestrian",
    )
    assert cached is result
    assert len(requests) == 1


def test_here_route_provider_returns_none_for_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FailingClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def get(self, url: str, *, params: dict[str, str]) -> httpx.Response:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(429, request=request)

    monkeypatch.setattr(
        "app.integrations.routing.here.httpx.Client",
        FailingClient,
    )
    provider = HereRouteProvider(
        base_url="https://router.example.test",
        api_key="secret-key",
        min_interval_seconds=0,
    )

    assert (
        provider.calculate(
            (21.0, 105.8),
            (21.1, 105.9),
            transport_mode="car",
        )
        is None
    )
