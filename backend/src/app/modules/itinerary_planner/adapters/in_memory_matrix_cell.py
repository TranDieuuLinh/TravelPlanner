from __future__ import annotations

from collections import OrderedDict
from time import monotonic

from app.modules.itinerary_planner.ports import MatrixCellCacheKey
from app.modules.itinerary_planner.routing_models import MatrixCell


class InMemoryMatrixCellCache:
    def __init__(
        self,
        *,
        max_entries: int = 100_000,
        ttl_seconds: float = 3600,
        unreachable_ttl_seconds: float = 600,
    ) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.unreachable_ttl_seconds = unreachable_ttl_seconds
        self._entries: OrderedDict[
            MatrixCellCacheKey, tuple[float, MatrixCell]
        ] = OrderedDict()

    async def get_many(
        self, keys: tuple[MatrixCellCacheKey, ...]
    ) -> dict[MatrixCellCacheKey, MatrixCell]:
        now = monotonic()
        result: dict[MatrixCellCacheKey, MatrixCell] = {}
        for key in keys:
            entry = self._entries.get(key)
            if entry is None:
                continue
            expires_at, cell = entry
            if expires_at <= now:
                self._entries.pop(key, None)
                continue
            self._entries.move_to_end(key)
            result[key] = cell
        return result

    async def put_many(
        self, values: dict[MatrixCellCacheKey, MatrixCell]
    ) -> None:
        now = monotonic()
        for key, cell in values.items():
            ttl = self.ttl_seconds if cell.reachable else self.unreachable_ttl_seconds
            self._entries[key] = (now + ttl, cell)
            self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
