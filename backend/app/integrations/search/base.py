from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    uri: str
    snippet: str


class WebSearchProvider(Protocol):
    provider_name: str

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]: ...
