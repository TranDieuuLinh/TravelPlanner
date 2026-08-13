import asyncio

import httpx
import pytest

from app.modules.itinerary_planner.adapters.valhalla import ValhallaAdapter
from app.modules.itinerary_planner.routing_models import (
    MatrixLocation,
    RouteLegRequest,
    RoutingErrorCode,
    RoutingPhaseError,
)


LOCATIONS = (
    MatrixLocation("a", 21.0, 105.8, "geo:a"),
    MatrixLocation("b", 21.1, 105.9, "geo:b"),
)


def test_parses_valhalla_directed_matrix_and_converts_km() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sources_to_targets"
        return httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [{"time": 0, "distance": 0}, {"time": 300, "distance": 1.2}],
                    [{"time": 420, "distance": 1.5}, {"time": 0, "distance": 0}],
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaAdapter("https://valhalla.test", client=client)

    matrix = asyncio.run(adapter.matrix(LOCATIONS, "auto"))
    asyncio.run(client.aclose())

    assert matrix.cell("a", "b").duration_seconds == 300
    assert matrix.cell("b", "a").duration_seconds == 420
    assert matrix.cell("a", "b").distance_meters == 1200


def test_null_cell_is_unreachable_and_invalid_shape_is_rejected() -> None:
    responses = iter(
        [
            {"sources_to_targets": [[{"time": 0, "distance": 0}, {}], [{}, {"time": 0, "distance": 0}]]},
            {"sources_to_targets": [[]]},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaAdapter("https://valhalla.test", client=client)

    matrix = asyncio.run(adapter.matrix(LOCATIONS, "auto"))
    assert matrix.cell("a", "b").reachable is False
    with pytest.raises(RoutingPhaseError) as error:
        asyncio.run(adapter.matrix(LOCATIONS, "auto"))
    asyncio.run(client.aclose())
    assert error.value.code == RoutingErrorCode.matrix_invalid_response


def test_route_detail_returns_only_requested_leg_geometry() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/route"
        return httpx.Response(
            200,
            json={
                "trip": {
                    "summary": {"time": 360, "length": 1.4},
                    "legs": [{"shape": "encoded-shape"}],
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaAdapter("https://valhalla.test", client=client)

    details = asyncio.run(
        adapter.route((RouteLegRequest(LOCATIONS[0], LOCATIONS[1]),), "auto")
    )
    asyncio.run(client.aclose())

    assert details[0].duration_seconds == 360
    assert details[0].distance_meters == 1400
    assert details[0].encoded_polyline == "encoded-shape"
