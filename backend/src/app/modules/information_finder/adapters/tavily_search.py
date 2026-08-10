import asyncio
from datetime import datetime, timezone
from typing import Any

from app.modules.information_finder.contract import SearchResponse, SearchResult
from app.modules.information_finder.ports import (
    SearchProviderError,
    SearchProviderQuotaExceeded,
    SearchProviderTimeout,
    SearchProviderUnauthorized,
)


class TavilySearchProvider:
    def __init__(
        self,
        api_key: str,
        *,
        search_depth: str = "basic",
        max_results: int = 5,
        timeout_seconds: float = 15.0,
        client: Any | None = None,
    ) -> None:
        if client is None:
            try:
                from tavily import AsyncTavilyClient  # type: ignore[import-untyped]
            except ImportError as exc:
                raise RuntimeError(
                    "tavily-python is required for Tavily search"
                ) from exc
            client = AsyncTavilyClient(api_key=api_key)
        self.client = client
        self.search_depth = search_depth
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str) -> SearchResponse:
        try:
            payload = await asyncio.wait_for(
                self.client.search(
                    query=query,
                    search_depth=self.search_depth,
                    max_results=self.max_results,
                    include_raw_content="text",
                    include_answer=False,
                ),
                timeout=self.timeout_seconds,
            )
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise SearchProviderTimeout("Tavily search timed out") from exc
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            message = str(exc).casefold()
            if status == 401 or "401" in message or "unauthorized" in message:
                raise SearchProviderUnauthorized(
                    "Tavily authentication failed"
                ) from exc
            if status == 429 or any(
                term in message for term in ("429", "quota", "limit")
            ):
                raise SearchProviderQuotaExceeded(
                    "Tavily quota or rate limit reached"
                ) from exc
            raise SearchProviderError("Tavily search failed") from exc

        fetched_at = datetime.now(timezone.utc)
        request_id = payload.get("request_id")
        results = []
        for item in payload.get("results", []):
            content = item.get("raw_content") or item.get("content") or ""
            results.append(
                SearchResult(
                    title=item.get("title") or item.get("url") or "Untitled source",
                    url=item.get("url", ""),
                    content=content,
                    provider_score=item.get("score"),
                    provider_request_id=request_id,
                    provider_external_id=item.get("id"),
                    published_at=item.get("published_date"),
                    source_updated_at=item.get("updated_at"),
                    fetched_at=fetched_at,
                )
            )
        return SearchResponse(results=results, provider_request_id=request_id)
