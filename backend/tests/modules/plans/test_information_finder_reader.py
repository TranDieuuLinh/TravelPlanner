import asyncio
from datetime import datetime, timezone

from app.modules.knowledge_graph.place_search import KnowledgeGraphPlaceMatch
from app.modules.plans.information_finder import InformationFinderReader


FIXED_NOW = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)


def graph_match(identity: str, name: str = "Cafe") -> KnowledgeGraphPlaceMatch:
    return KnowledgeGraphPlaceMatch(
        entity_id=identity,
        name=name,
        entity_type="Restaurant",
        status="verified",
        address="Hanoi",
        latitude=21.0,
        longitude=105.0,
    )


class FakeGraph:
    def __init__(self, results: list[KnowledgeGraphPlaceMatch]) -> None:
        self.results = results
        self.calls: list[tuple[str, str | None, int]] = []

    def search(self, query: str, destination: str | None, *, limit: int):
        self.calls.append((query, destination, limit))
        return self.results[:limit]


class FakeProvider:
    provider_name = "fake_maps"

    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = results or []
        self.error = error
        self.calls = 0

    async def search(self, query, destination, top_k, filters=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.results[:top_k]


def reader(graph, provider=None):
    return InformationFinderReader(graph, provider, clock=lambda: FIXED_NOW)


def test_graph_results_fill_top_k_without_calling_provider():
    provider = FakeProvider([{"place_id": "external-1", "name": "Other"}])
    result = asyncio.run(reader(
        FakeGraph([graph_match("graph-1"), graph_match("graph-2")]), provider
    ).search(
        "cafe", "Hanoi", 2, {}
    ))

    assert [candidate.place_id for candidate in result.candidates] == ["graph-1", "graph-2"]
    assert provider.calls == 0
    assert all(candidate.is_verified for candidate in result.candidates)


def test_graph_shortfall_merges_provider_and_deduplicates_identity():
    provider = FakeProvider(
        [
            {"place_id": "graph-1", "name": "Cafe", "latitude": 21, "longitude": 105},
            {
                "place_id": "external-1",
                "name": "Other",
                "latitude": 21.1,
                "longitude": 105.1,
                "fetched_at": "2025-01-01T00:00:00Z",
            },
        ]
    )
    result = asyncio.run(reader(FakeGraph([graph_match("graph-1")]), provider).search(
        "cafe", "Hanoi", 3, {"placeType": "Restaurant"}
    ))

    assert [candidate.place_id for candidate in result.candidates] == ["graph-1", "external-1"]
    assert result.candidates[-1].is_verified is False
    assert result.candidates[-1].fetched_at == datetime(2025, 1, 1, tzinfo=timezone.utc)


def test_provider_failure_returns_structured_warning_and_graph_results():
    result = asyncio.run(reader(
        FakeGraph([graph_match("graph-1")]), FakeProvider(error=TimeoutError())
    ).search("cafe", "Hanoi", 3))

    assert len(result.candidates) == 1
    assert result.warnings == ["provider_search_failed:fake_maps"]


def test_empty_query_does_not_read_or_write():
    graph = FakeGraph([graph_match("graph-1")])
    provider = FakeProvider()
    finder = reader(graph, provider)
    result = asyncio.run(finder.search("  ", None, 5))

    assert result.kind == "empty"
    assert result.candidates == []
    assert graph.calls == []
    assert provider.calls == 0
    assert not any(hasattr(finder, method) for method in ("add_item", "update_item", "remove_item"))


def test_graph_source_timestamp_is_propagated_when_present():
    match = graph_match("graph-old")
    match = KnowledgeGraphPlaceMatch(
        **{**match.__dict__, "source_fetched_at": "2024-02-03T04:05:06Z"}
    )
    result = asyncio.run(reader(FakeGraph([match])).search("cafe", None, 1))

    assert result.candidates[0].fetched_at == datetime(2024, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
