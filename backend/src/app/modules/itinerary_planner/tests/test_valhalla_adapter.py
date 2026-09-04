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
    invalid_adapter = ValhallaAdapter("https://valhalla.test", client=client)
    with pytest.raises(RoutingPhaseError) as error:
        asyncio.run(invalid_adapter.matrix(LOCATIONS, "auto"))
    asyncio.run(client.aclose())
    assert error.value.code == RoutingErrorCode.matrix_invalid_response


def test_pair_cache_only_requests_missing_pairs_for_overlapping_location_sets() -> None:
    request_pair_counts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        sources = payload["sources"]
        targets = payload["targets"]
        request_pair_counts.append(len(sources) * len(targets))
        return httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [{"time": 60, "distance": 1} for _ in targets]
                    for _ in sources
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaAdapter("https://valhalla.test", client=client)
    first_locations = (
        MatrixLocation("a", 21.0, 105.8, "geo:a"),
        MatrixLocation("b", 21.1, 105.9, "geo:b"),
        MatrixLocation("c", 21.2, 106.0, "geo:c"),
    )
    second_locations = (
        MatrixLocation("a", 21.0, 105.8, "geo:a"),
        MatrixLocation("b", 21.1, 105.9, "geo:b"),
        MatrixLocation("d", 21.3, 106.1, "geo:d"),
    )

    first = asyncio.run(adapter.matrix(first_locations, "auto"))
    second = asyncio.run(adapter.matrix(second_locations, "auto"))
    asyncio.run(client.aclose())

    assert first.logical_pair_count == 6
    assert first.pair_cache_hit_count == 0
    assert second.logical_pair_count == 6
    assert second.pair_cache_hit_count == 2
    assert second.provider_pair_count == 4
    assert sum(request_pair_counts[1:]) == 4


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


def test_successful_matrix_batches_are_reused_after_one_batch_fails() -> None:
    locations = tuple(
        MatrixLocation(str(index), 21.0 + index / 10, 105.8, f"geo:{index}")
        for index in range(3)
    )
    requests: list[tuple[tuple[float, ...], tuple[float, ...]]] = []
    failed_once = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal failed_once
        payload = json.loads(request.content)
        sources = tuple(item["lat"] for item in payload["sources"])
        targets = tuple(item["lat"] for item in payload["targets"])
        requests.append((sources, targets))
        if (
            sources == (21.2,)
            and targets == (21.0, 21.1, 21.2)
            and not failed_once
        ):
            failed_once = True
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "sources_to_targets": [
                    [{"time": 60, "distance": 1} for _ in targets]
                    for _ in sources
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = ValhallaAdapter(
        "https://valhalla.test",
        client=client,
        max_matrix_pairs=4,
    )

    with pytest.raises(RoutingPhaseError):
        asyncio.run(adapter.matrix(locations, "auto"))
    first_call_count = len(requests)
    matrix = asyncio.run(adapter.matrix(locations, "auto"))
    asyncio.run(client.aclose())

    assert first_call_count == 3
    assert len(requests) == first_call_count + 1
    assert matrix.node_ids == tuple(str(index) for index in range(3))


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
