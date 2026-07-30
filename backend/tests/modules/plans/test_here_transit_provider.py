from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import pytest

from app.integrations.routing.here_transit import HereTransitRouteProvider


EXAMPLE_POLYLINE = "BFoz5xJ67i1B1B7PzIhaxL7Y"


def test_here_transit_provider_selects_transit_route_and_includes_waits(
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
                                _section(
                                    section_type="pedestrian",
                                    mode="pedestrian",
                                    duration=900,
                                    length=800,
                                )
                            ]
                        },
                        {
                            "sections": [
                                _section(
                                    section_type="pedestrian",
                                    mode="pedestrian",
                                    duration=180,
                                    length=150,
                                    departure="2026-08-01T09:00:00+07:00",
                                ),
                                _section(
                                    section_type="transit",
                                    mode="bus",
                                    duration=420,
                                    length=3200,
                                    line="31",
                                ),
                                _section(
                                    section_type="pedestrian",
                                    mode="pedestrian",
                                    duration=120,
                                    length=100,
                                    arrival="2026-08-01T09:15:00+07:00",
                                ),
                            ]
                        },
                    ]
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.here_transit.httpx.Client",
        FakeClient,
    )
    provider = HereTransitRouteProvider(
        base_url="https://transit.example.test",
        api_key="secret-key",
        min_interval_seconds=0,
    )

    result = provider.calculate(
        (21.0, 105.8),
        (21.1, 105.9),
        departure_time=_departure(),
    )

    assert result is not None
    assert result.distance_meters == 3450
    assert result.duration_seconds == 900
    assert result.provider == "here_transit_v8"
    assert result.details == {"transitModes": ["bus"], "lines": ["31"]}
    assert len(result.geometry_coordinates) == 12
    assert len(requests) == 1
    params = requests[0].url.params
    assert params["departureTime"] == "2026-08-01T09:00:00"
    assert params["pedestrian[maxDistance]"] == "1500"

    current_result = provider.calculate(
        (21.01, 105.81),
        (21.11, 105.91),
        departure_time=None,
    )

    assert current_result is not None
    assert len(requests) == 2
    assert "departureTime" not in requests[1].url.params


def test_here_transit_provider_rejects_pedestrian_only_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_: Any) -> None:
            return None

        def get(self, url: str, *, params: dict[str, str]) -> httpx.Response:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(
                200,
                request=request,
                json={
                    "routes": [
                        {
                            "sections": [
                                _section(
                                    section_type="pedestrian",
                                    mode="pedestrian",
                                    duration=600,
                                    length=500,
                                )
                            ]
                        }
                    ]
                },
            )

    monkeypatch.setattr(
        "app.integrations.routing.here_transit.httpx.Client",
        FakeClient,
    )
    provider = HereTransitRouteProvider(
        base_url="https://transit.example.test",
        api_key="secret-key",
        min_interval_seconds=0,
    )

    assert (
        provider.calculate(
            (21.0, 105.8),
            (21.1, 105.9),
            departure_time=_departure(),
        )
        is None
    )


def _departure() -> datetime:
    return datetime(2026, 8, 1, 9, 0)


def _section(
    *,
    section_type: str,
    mode: str,
    duration: int,
    length: int,
    line: str | None = None,
    departure: str | None = None,
    arrival: str | None = None,
) -> dict[str, Any]:
    section: dict[str, Any] = {
        "type": section_type,
        "transport": {"mode": mode},
        "travelSummary": {
            "duration": duration,
            "length": length,
        },
        "polyline": EXAMPLE_POLYLINE,
    }
    if line is not None:
        section["transport"]["shortName"] = line
    if departure is not None:
        section["departure"] = {"time": departure}
    if arrival is not None:
        section["arrival"] = {"time": arrival}
    return section
