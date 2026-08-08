"""Crawl public admission-price pages and optionally persist grounded prices.

This batch command reuses TravelPlanner's public web-page reader
(``httpx`` + Trafilatura) after a search provider discovers candidate pages.
Gemini only extracts a structured price from the downloaded text. Verified
results are written through the existing Knowledge Graph repository and keep
the final page URL as provenance.

The command is a dry-run unless ``--apply`` is provided.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from pathlib import Path


REPOSITORY_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPOSITORY_DIR / "backend"
PRICE_TOOL_DIR = REPOSITORY_DIR / "tool-crawl" / "crawl-price"
for import_path in (BACKEND_DIR, PRICE_TOOL_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.integrations.llm.provider import GeminiLLMClient  # noqa: E402
from app.integrations.search.base import (  # noqa: E402
    WebSearchProvider,
    WebSearchResult,
)
from app.modules.plans.explorer.tools.web_page.service import (  # noqa: E402
    WebPageFetcher,
)
from app.shared.errors import AppError  # noqa: E402
from enrich_travel_place_prices import (  # noqa: E402
    append_cache,
    apply_outcomes,
    count_admission_prices,
    fetch_outcomes,
    is_terminal_cached_outcome,
    load_cache,
    load_candidates,
)


class MainTextPageSearchProvider:
    """Decorate search results with safely fetched, distilled page text."""

    def __init__(
        self,
        search_provider: WebSearchProvider,
        *,
        fetcher: WebPageFetcher | None = None,
        max_pages: int = 3,
        max_content_chars: int = 20_000,
        crawl_delay_seconds: float = 5.0,
        allow_search_snippet_fallback: bool = True,
    ) -> None:
        self.search_provider = search_provider
        self.fetcher = fetcher or WebPageFetcher()
        self.max_pages = max(1, min(max_pages, 5))
        self.max_content_chars = max(1_000, min(max_content_chars, 50_000))
        self.crawl_delay_seconds = max(0.0, min(crawl_delay_seconds, 300.0))
        self.allow_search_snippet_fallback = allow_search_snippet_fallback
        self.provider_name = f"{search_provider.provider_name}_main_text"
        self.stats: Counter[str] = Counter()
        self._fetch_interval_lock = asyncio.Lock()
        self._last_fetch_started_at = 0.0

    async def _wait_for_fetch_interval(self) -> None:
        async with self._fetch_interval_lock:
            remaining = (
                self._last_fetch_started_at
                + self.crawl_delay_seconds
                - time.monotonic()
            )
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_fetch_started_at = time.monotonic()

    async def search(self, query: str, *, limit: int) -> list[WebSearchResult]:
        discovered = await self.search_provider.search(
            query,
            limit=min(max(1, limit), self.max_pages),
        )
        output: list[WebSearchResult] = []
        for result in discovered[: self.max_pages]:
            await self._wait_for_fetch_interval()
            try:
                document = await asyncio.to_thread(self.fetcher.fetch, result.uri)
            except AppError as exc:
                self.stats[f"page_error:{exc.code}"] += 1
                snippet = result.snippet.strip()
                if self.allow_search_snippet_fallback and snippet:
                    output.append(
                        WebSearchResult(
                            title=result.title,
                            uri=result.uri,
                            snippet=snippet[: self.max_content_chars],
                        )
                    )
                    self.stats["search_snippet_fallback"] += 1
                continue

            output.append(
                WebSearchResult(
                    title=(document.title or result.title or document.url)[:500],
                    uri=document.url[:2048],
                    snippet=document.text[: self.max_content_chars],
                )
            )
            self.stats["page_main_text_fetched"] += 1
        return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit verified prices; default is DB dry-run.",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--min-review-count", type=int, default=0)
    parser.add_argument(
        "--place-type",
        action="append",
        default=[],
        help="Only include this exact place_type; may be repeated.",
    )
    parser.add_argument(
        "--search-provider",
        choices=("google_selenium", "tavily"),
        default=(
            settings.price_search_provider
            if settings.price_search_provider in {"google_selenium", "tavily"}
            else "google_selenium"
        ),
    )
    parser.add_argument("--max-pages-per-place", type=int, default=3)
    parser.add_argument("--max-page-chars", type=int, default=20_000)
    parser.add_argument(
        "--crawl-delay-seconds",
        type=float,
        default=5.0,
        help="Minimum delay between target-page download starts.",
    )
    parser.add_argument(
        "--strict-static",
        action="store_true",
        help="Do not fall back to provider snippets when static page fetch fails.",
    )
    parser.add_argument(
        "--min-interval-seconds",
        type=float,
        default=settings.gemini_price_min_interval_seconds,
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=BACKEND_DIR / "var" / "admission-price-main-text-v1.jsonl",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore terminal cached outcomes and research again.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing admission_price property.",
    )
    parser.add_argument("--no-cache-write", action="store_true")
    parser.add_argument(
        "--model",
        default=settings.gemini_price_model or settings.gemini_model,
    )
    return parser.parse_args()


def _base_search_provider(name: str) -> WebSearchProvider:
    if name == "tavily":
        if not settings.tavily_api_key:
            raise SystemExit("TAVILY_API_KEY is required for --search-provider=tavily")
        from app.integrations.search.tavily import TavilySearchProvider

        return TavilySearchProvider(
            settings.tavily_api_key,
            timeout_seconds=settings.tavily_timeout_seconds,
        )

    from app.integrations.search.google_selenium import GoogleSeleniumSearchProvider

    return GoogleSeleniumSearchProvider(
        timeout_seconds=settings.google_web_search_timeout_seconds,
        min_interval_seconds=settings.google_web_search_min_interval_seconds,
        page_load_wait_seconds=settings.google_selenium_page_load_wait_seconds,
        post_search_delay_seconds=settings.google_selenium_post_search_delay_seconds,
    )


def _validate_args(args: argparse.Namespace) -> None:
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.min_review_count < 0:
        raise SystemExit("--min-review-count cannot be negative")
    if not 1 <= args.max_pages_per_place <= 5:
        raise SystemExit("--max-pages-per-place must be between 1 and 5")
    if not 1_000 <= args.max_page_chars <= 50_000:
        raise SystemExit("--max-page-chars must be between 1000 and 50000")
    if not 0 <= args.crawl_delay_seconds <= 300:
        raise SystemExit("--crawl-delay-seconds must be between 0 and 300")
    if not 0 <= args.min_interval_seconds <= 60:
        raise SystemExit("--min-interval-seconds must be between 0 and 60")
    if not settings.gemini_price_key_pool:
        raise SystemExit(
            "GEMINI_PRICE_API_KEYS or GEMINI_API_KEY is missing from backend/.env"
        )


def main() -> int:
    args = parse_args()
    _validate_args(args)
    aggregate: Counter[str] = Counter()
    session = SessionLocal()
    page_provider: MainTextPageSearchProvider | None = None
    try:
        records = load_candidates(
            session,
            min_review_count=args.min_review_count,
            place_types=set(args.place_type),
            overwrite=args.overwrite,
        )
        cache = load_cache(args.cache_file)
        aggregate["eligible"] = len(records)

        cached_applicable = [
            cache[record.candidate.entity_id]
            for record in records
            if record.candidate.entity_id in cache
            and cache[record.candidate.entity_id].can_apply
            and not args.refresh
        ]
        if cached_applicable:
            aggregate.update(
                apply_outcomes(
                    session,
                    cached_applicable,
                    apply=args.apply,
                    overwrite=args.overwrite,
                )
            )

        pending = [
            record
            for record in records
            if args.refresh
            or record.candidate.entity_id not in cache
            or not is_terminal_cached_outcome(cache[record.candidate.entity_id])
        ][: args.limit]
        aggregate["scheduled"] = len(pending)

        page_provider = MainTextPageSearchProvider(
            _base_search_provider(args.search_provider),
            max_pages=args.max_pages_per_place,
            max_content_chars=args.max_page_chars,
            crawl_delay_seconds=args.crawl_delay_seconds,
            allow_search_snippet_fallback=not args.strict_static,
        )
        llm_client = GeminiLLMClient(
            settings.gemini_price_key_pool,
            args.model,
            min_interval_seconds=args.min_interval_seconds,
        )

        def persist_outcome(outcome) -> None:
            if not args.no_cache_write:
                append_cache(args.cache_file, [outcome])
                aggregate["cache_records_written"] += 1
            aggregate[outcome.status.value] += 1
            if outcome.error:
                aggregate[f"error:{outcome.error}"] += 1
            aggregate.update(
                apply_outcomes(
                    session,
                    [outcome],
                    apply=args.apply,
                    overwrite=args.overwrite,
                )
            )

        outcomes = asyncio.run(
            fetch_outcomes(
                pending,
                llm_client=llm_client,
                model_name=args.model,
                concurrency=1,
                search_provider=page_provider,
                on_outcome=persist_outcome,
            )
        )
        quota_deferred = len(pending) - len(outcomes)
        if quota_deferred > 0 and any(
            outcome.error == "gemini_quota_limited" for outcome in outcomes
        ):
            aggregate["quota_limited_deferred"] += quota_deferred
        aggregate.update(page_provider.stats)
        aggregate["admission_price_in_database"] = count_admission_prices(session)
    finally:
        session.close()

    print(
        json.dumps(
            {
                "status": "applied" if args.apply else "dry_run",
                "cacheFile": str(args.cache_file),
                "searchProvider": (
                    page_provider.provider_name if page_provider else args.search_provider
                ),
                **dict(sorted(aggregate.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
