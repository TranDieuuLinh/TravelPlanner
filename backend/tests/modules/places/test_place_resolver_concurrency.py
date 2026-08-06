import asyncio
import threading
import time
from contextlib import contextmanager

from app.modules.places.resolver import KnowledgeGraphPlaceResolver
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


class _ConcurrencyProbe:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.active = 0
        self.maximum_active = 0
        self.opened = 0
        self.closed = 0

    def search(self) -> None:
        with self.lock:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
        time.sleep(0.05)
        with self.lock:
            self.active -= 1


class _WorkerRepository:
    def __init__(self, probe: _ConcurrencyProbe) -> None:
        self.probe = probe

    def search_active_by_names(self, names: list[str], *, limit: int = 100):
        self.probe.search()
        return []


def test_knowledge_graph_resolver_uses_four_isolated_workers() -> None:
    probe = _ConcurrencyProbe()

    @contextmanager
    def repository_context():
        with probe.lock:
            probe.opened += 1
        try:
            yield _WorkerRepository(probe)
        finally:
            with probe.lock:
                probe.closed += 1

    resolver = KnowledgeGraphPlaceResolver(
        _WorkerRepository(probe),
        max_concurrency=4,
        repository_context_factory=repository_context,
    )
    candidates = [
        UnifiedPlaceCandidate(name=f"Candidate {index}", searchRegion="Hà Nội")
        for index in range(8)
    ]

    results = asyncio.run(resolver.resolve_many(candidates, destination="Hà Nội"))

    assert len(results) == 8
    assert probe.maximum_active == 4
    assert probe.opened == 8
    assert probe.closed == 8

