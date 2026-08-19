from __future__ import annotations

from collections import OrderedDict
from time import monotonic

from app.modules.itinerary_planner.routing_models import MatrixLocation, TravelMatrix


class InMemoryMatrixCache:
    def __init__(self, *, max_entries: int = 32, ttl_seconds: float = 900) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[str, tuple[float, TravelMatrix]] = OrderedDict()

    async def get(self, key: str) -> TravelMatrix | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, matrix = entry
        if expires_at <= monotonic():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return matrix

    async def put(self, key: str, matrix: TravelMatrix) -> None:
        self._entries[key] = (monotonic() + self.ttl_seconds, matrix)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


class StaticMatrixProvider:
    """Deterministic provider for tests; never estimates missing pairs."""

    def __init__(self, matrix: TravelMatrix) -> None:
        self.value = matrix
        self.calls = 0

    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        self.calls += 1
        requested = tuple(location.node_id for location in locations)
        if requested != self.value.node_ids or profile != self.value.profile:
            raise ValueError("Static matrix does not match requested nodes/profile")
        return self.value
