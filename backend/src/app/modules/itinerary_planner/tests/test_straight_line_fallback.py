import asyncio

import httpx

from app.modules.itinerary_planner.adapters.fallback import FallbackRoutingAdapter
from app.modules.itinerary_planner.adapters.straight_line import (
    StraightLineRoutingAdapter,
)
from app.modules.itinerary_planner.adapters.valhalla import ValhallaAdapter
from app.modules.itinerary_planner.routing_models import MatrixLocation, RouteLegRequest


LOCATIONS = (
    MatrixLocation("a", 21.0, 105.8, "geo:a"),
    MatrixLocation("b", 21.1, 105.9, "geo:b"),
)


def test_straight_line_provider_builds_matrix_and_direct_polyline() -> None:
    provider = StraightLineRoutingAdapter()

    matrix = asyncio.run(provider.matrix(LOCATIONS, "auto"))
    details = asyncio.run(
        provider.route((RouteLegRequest(LOCATIONS[0], LOCATIONS[1]),), "auto")
    )

    cell = matrix.cell("a", "b")
    assert matrix.provider == "straight_line_fallback"
    assert cell.reachable is True
    assert 15_000 < cell.distance_meters < 16_000
    assert details[0].encoded_polyline
    assert details[0].distance_meters == cell.distance_meters


def test_fallback_provider_uses_straight_line_when_valhalla_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Valhalla unavailable", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    primary = ValhallaAdapter("http://valhalla:8002", client=client)
    adapter = FallbackRoutingAdapter(primary, StraightLineRoutingAdapter())

    matrix = asyncio.run(adapter.matrix(LOCATIONS, "auto"))
    asyncio.run(client.aclose())

    assert matrix.provider == "straight_line_fallback"


def test_route_fallback_returns_direct_polyline_when_valhalla_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Valhalla unavailable", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    primary = ValhallaAdapter("http://valhalla:8002", client=client)
    adapter = FallbackRoutingAdapter(primary, StraightLineRoutingAdapter())

    details = asyncio.run(
        adapter.route((RouteLegRequest(LOCATIONS[0], LOCATIONS[1]),), "auto")
    )
    asyncio.run(client.aclose())

    assert details[0].provider == "straight_line_fallback"
    assert details[0].encoded_polyline
