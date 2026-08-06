from __future__ import annotations

import httpx

from .base import WebSearchResult


class TavilySearchProvider:
    provider_name = "tavily"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        if not self.api_key:
            raise ValueError("Tavily API key is required.")
        self.timeout_seconds = max(5.0, timeout_seconds)
        self.transport = transport

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        cleaned = query.strip()
        if not cleaned:
            return []
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            transport=self.transport,
            trust_env=False,
        ) as client:
            try:
                response = await client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "query": cleaned,
                        "topic": "general",
                        "search_depth": "basic",
                        "max_results": max(1, min(limit, 10)),
                        "include_answer": False,
                        "include_images": False,
                        "include_raw_content": False,
                        "country": "vietnam",
                    },
                )
            except httpx.RequestError as exc:
                raise RuntimeError("tavily_network_error") from exc
        if response.status_code in {401, 403}:
            raise RuntimeError("tavily_key_rejected")
        if response.status_code == 429:
            raise RuntimeError("tavily_quota_limited")
        if response.is_error:
            raise RuntimeError(f"tavily_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("tavily_invalid_response") from exc

        results: list[WebSearchResult] = []
        seen: set[str] = set()
        for item in payload.get("results") or []:
            uri = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()
            if not uri or not title or uri in seen:
                continue
            seen.add(uri)
            results.append(
                WebSearchResult(
                    title=title[:500],
                    uri=uri[:2048],
                    snippet=str(item.get("content") or "").strip()[:2000],
                )
            )
            if len(results) >= max(1, min(limit, 10)):
                break
        return results
