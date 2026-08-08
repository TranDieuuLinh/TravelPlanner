from __future__ import annotations

import asyncio
import sys
from pathlib import Path


CRAWL_DATA_DIR = Path(__file__).resolve().parents[3] / "crawl_data"
if str(CRAWL_DATA_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWL_DATA_DIR))

from app.integrations.search.base import WebSearchResult  # noqa: E402
from app.modules.plans.explorer.tools.web_page.service import (  # noqa: E402
    WebPageDocument,
)
from app.shared.errors import AppError  # noqa: E402
import crawl_admission_prices as crawler  # noqa: E402


MainTextPageSearchProvider = crawler.MainTextPageSearchProvider


class FakeSearchProvider:
    provider_name = "fake_search"

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        assert query == "giá vé của Văn Miếu"
        assert limit == 2
        return [
            WebSearchResult(
                title="Search title",
                uri="https://official.example/tickets?utm_source=search",
                snippet="Short search snippet",
            )
        ]


class FakePageFetcher:
    def fetch(self, url: str) -> WebPageDocument:
        assert url == "https://official.example/tickets?utm_source=search"
        return WebPageDocument(
            url="https://official.example/tickets",
            title="Official admission tickets",
            text="Standard adult daytime admission is 70,000 VND.",
            description=None,
        )


def test_provider_downloads_main_text_and_preserves_final_source_url() -> None:
    provider = MainTextPageSearchProvider(
        FakeSearchProvider(),  # type: ignore[arg-type]
        fetcher=FakePageFetcher(),  # type: ignore[arg-type]
        max_pages=2,
        crawl_delay_seconds=0,
    )

    results = asyncio.run(provider.search("giá vé của Văn Miếu", limit=8))

    assert results == [
        WebSearchResult(
            title="Official admission tickets",
            uri="https://official.example/tickets",
            snippet="Standard adult daytime admission is 70,000 VND.",
        )
    ]
    assert provider.stats["page_main_text_fetched"] == 1


class BlockedPageFetcher:
    def fetch(self, url: str) -> WebPageDocument:
        del url
        raise AppError(503, "WEB_PAGE_UNAVAILABLE", "blocked")


def test_provider_falls_back_to_search_snippet_when_page_is_blocked() -> None:
    provider = MainTextPageSearchProvider(
        FakeSearchProvider(),  # type: ignore[arg-type]
        fetcher=BlockedPageFetcher(),  # type: ignore[arg-type]
        max_pages=2,
        crawl_delay_seconds=0,
    )

    results = asyncio.run(provider.search("giá vé của Văn Miếu", limit=8))

    assert results[0].snippet == "Short search snippet"
    assert results[0].uri == "https://official.example/tickets?utm_source=search"
    assert provider.stats["page_error:WEB_PAGE_UNAVAILABLE"] == 1
    assert provider.stats["search_snippet_fallback"] == 1


def test_strict_static_drops_blocked_pages() -> None:
    provider = MainTextPageSearchProvider(
        FakeSearchProvider(),  # type: ignore[arg-type]
        fetcher=BlockedPageFetcher(),  # type: ignore[arg-type]
        max_pages=2,
        crawl_delay_seconds=0,
        allow_search_snippet_fallback=False,
    )

    assert asyncio.run(provider.search("giá vé của Văn Miếu", limit=8)) == []


class TwoResultSearchProvider:
    provider_name = "two_results"

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        del query, limit
        return [
            WebSearchResult(
                title=f"Source {index}",
                uri=f"https://official.example/tickets/{index}",
                snippet="Price evidence",
            )
            for index in range(2)
        ]


class PassthroughPageFetcher:
    def fetch(self, url: str) -> WebPageDocument:
        return WebPageDocument(
            url=url,
            title="Official tickets",
            text="Adult admission is 70,000 VND.",
            description=None,
        )


def test_provider_waits_between_target_page_downloads(monkeypatch) -> None:
    clock = {"now": 100.0}
    delays: list[float] = []

    def monotonic() -> float:
        return clock["now"]

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(crawler.time, "monotonic", monotonic)
    monkeypatch.setattr(crawler.asyncio, "sleep", fake_sleep)
    provider = MainTextPageSearchProvider(
        TwoResultSearchProvider(),  # type: ignore[arg-type]
        fetcher=PassthroughPageFetcher(),  # type: ignore[arg-type]
        max_pages=2,
        crawl_delay_seconds=5,
    )

    results = asyncio.run(provider.search("price", limit=8))

    assert len(results) == 2
    assert delays == [5.0]
