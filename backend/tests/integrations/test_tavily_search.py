from __future__ import annotations

import asyncio
import json

import httpx

from app.integrations.search.tavily import TavilySearchProvider


def test_tavily_normalizes_search_results_without_raw_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["search_depth"] == "basic"
        assert payload["include_raw_content"] is False
        assert payload["country"] == "vietnam"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Official tickets",
                        "url": "https://example.test/tickets",
                        "content": "Adult ticket 70,000 VND",
                        "raw_content": "must not cross the boundary",
                    }
                ]
            },
        )

    provider = TavilySearchProvider(
        "test-key",
        transport=httpx.MockTransport(handler),
    )
    results = asyncio.run(provider.search("ticket price", limit=8))

    assert results[0].uri == "https://example.test/tickets"
    assert results[0].snippet == "Adult ticket 70,000 VND"


def test_tavily_maps_quota_error_without_exposing_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(429, json={"detail": "secret provider payload"})

    provider = TavilySearchProvider(
        "test-key",
        transport=httpx.MockTransport(handler),
    )

    try:
        asyncio.run(provider.search("ticket price", limit=8))
    except RuntimeError as exc:
        assert str(exc) == "tavily_quota_limited"
    else:  # pragma: no cover
        raise AssertionError("Expected Tavily quota error")
