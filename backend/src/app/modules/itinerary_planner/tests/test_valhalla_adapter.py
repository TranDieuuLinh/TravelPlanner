import asyncio
import json

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


def test_large_matrix_is_batched_without_exceeding_provider_pair_limit() -> None:
    locations = tuple(
        MatrixLocation(str(index), 21.0 + index / 100, 105.8, f"geo:{index}")
        for index in range(5)
    )
    request_pair_counts = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        sources = payload["sources"]
        targets = payload["targets"]
        request_pair_counts.append(len(sources) * len(targets))
        return httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [
                        {
                            "time": round((source["lat"] - 21) * 100) * 100
                            + round((target["lat"] - 21) * 100),
                            "distance": 1,
                        }
                        for target in targets
                    ]
                    for source in sources
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaAdapter(
        "https://valhalla.test",
        client=client,
        max_matrix_pairs=6,
    )

    matrix = asyncio.run(adapter.matrix(locations, "auto"))
    asyncio.run(client.aclose())

    assert len(request_pair_counts) > 1
    assert max(request_pair_counts) <= 6
    assert matrix.node_ids == tuple(str(index) for index in range(5))
    assert matrix.cell("4", "1").duration_seconds == 401


def test_default_batches_cover_111_locations_with_at_most_2500_pairs() -> None:
    locations = tuple(
        MatrixLocation(str(index), 21.0 + index / 10_000, 105.8, f"geo:{index}")
        for index in range(111)
    )
    adapter = ValhallaAdapter("https://valhalla.test")

    batches = adapter._matrix_batches(locations)

    assert len(batches) == 6
    assert (
        max(len(sources) * len(targets) for _, sources, _, targets in batches)
        <= 2_500
    )


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
