import asyncio
from collections import OrderedDict


class InMemoryImageOcrCache:
    """Process-local OCR cache; keys contain only a digest of image bytes."""

    def __init__(self, *, max_entries: int = 256) -> None:
        if max_entries < 1:
            raise ValueError("Image OCR cache must keep at least one entry.")
        self.max_entries = max_entries
        self._items: OrderedDict[str, str] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, cache_key: str) -> str | None:
        async with self._lock:
            value = self._items.get(cache_key)
            if value is not None:
                self._items.move_to_end(cache_key)
            return value

    async def save(self, cache_key: str, text: str) -> None:
        async with self._lock:
            self._items[cache_key] = text
            self._items.move_to_end(cache_key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
