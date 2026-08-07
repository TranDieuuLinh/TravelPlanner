"""Research sourced admission prices for Knowledge Graph TravelPlace nodes.

The command uses either Gemini Google Search grounding or a configured web
search provider followed by structured Gemini extraction. It is resumable
through a JSONL cache, defaults to a database dry-run and only persists
schema-validated results that cite web sources.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session


REPOSITORY_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPOSITORY_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.integrations.llm.provider import GeminiLLMClient  # noqa: E402
from app.integrations.search.base import WebSearchProvider  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.price_research import (  # noqa: E402
    PriceResearchStatus,
    TravelPlacePriceCandidate,
    TravelPlacePriceOutcome,
    research_travel_place_price,
    research_travel_place_price_with_web_search,
)
from app.modules.knowledge_graph.repositories.kg_repository import (  # noqa: E402
    KnowledgeGraphRepository,
)


RESEARCH_PROPERTY_KEYS = {
    "address",
    "city",
    "country",
    "place_type",
    "source_url",
    "review_count",
    "admission_price",
}
TERMINAL_CACHE_STATUSES = {
    PriceResearchStatus.not_found,
    PriceResearchStatus.ambiguous,
}


@dataclass(frozen=True)
class CandidateRecord:
    candidate: TravelPlacePriceCandidate
    has_existing_price: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit verified prices; default only researches and caches results.",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument(
        "--search-provider",
        choices=("google_selenium", "gemini_grounded", "tavily"),
        default=settings.price_search_provider,
    )
    parser.add_argument(
        "--min-interval-seconds",
        type=float,
        default=settings.gemini_price_min_interval_seconds,
        help="Minimum delay between Gemini request starts; default is 4 seconds.",
    )
    parser.add_argument("--min-review-count", type=int, default=0)
    parser.add_argument(
        "--place-type",
        action="append",
        default=[],
        help="Only include this exact place_type; may be repeated.",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=BACKEND_DIR / "var" / "travel-place-price-research-v1.jsonl",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore terminal cached outcomes and research again.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing admission-price property.",
    )
    parser.add_argument(
        "--no-cache-write",
        action="store_true",
        help="Do not append newly researched outcomes to the resume cache.",
    )
    parser.add_argument(
        "--model",
        default=settings.gemini_price_model or settings.gemini_model,
    )
    return parser.parse_args()


def load_candidates(
    session: Session,
    *,
    min_review_count: int = 0,
    place_types: set[str] | None = None,
    overwrite: bool = False,
) -> list[CandidateRecord]:
    rows = session.execute(
        select(KnowledgeEntity, KnowledgeProperty)
        .outerjoin(
            KnowledgeProperty,
            and_(
                KnowledgeProperty.entity_id == KnowledgeEntity.id,
                KnowledgeProperty.key.in_(RESEARCH_PROPERTY_KEYS),
            ),
        )
        .where(KnowledgeEntity.entity_type == "TravelPlace")
        .order_by(KnowledgeEntity.id)
    )
    entities: dict[str, KnowledgeEntity] = {}
    properties: dict[str, dict[str, str]] = defaultdict(dict)
    for entity, prop in rows:
        entities[entity.id] = entity
        if prop is not None:
            properties[entity.id][prop.key] = prop.value

    normalized_types = {
        value.strip().casefold() for value in (place_types or set()) if value.strip()
    }
    candidates: list[CandidateRecord] = []
    for entity in entities.values():
        props = properties[entity.id]
        try:
            review_count = max(0, int(float(props.get("review_count", "0") or 0)))
        except ValueError:
            review_count = 0
        if review_count < min_review_count:
            continue
        place_type = (props.get("place_type") or "").strip()
        if normalized_types and place_type.casefold() not in normalized_types:
            continue
        has_existing_price = bool(props.get("admission_price"))
        if has_existing_price and not overwrite:
            continue
        candidates.append(
            CandidateRecord(
                candidate=TravelPlacePriceCandidate(
                    entityId=entity.id,
                    canonicalName=entity.canonical_name,
                    address=props.get("address") or None,
                    city=props.get("city") or None,
                    country=props.get("country") or None,
                    placeType=place_type or None,
                    sourceUrl=props.get("source_url") or None,
                    reviewCount=review_count,
                ),
                has_existing_price=has_existing_price,
            )
        )
    return sorted(
        candidates,
        key=lambda item: (-item.candidate.review_count, item.candidate.entity_id),
    )


def load_cache(path: Path) -> dict[str, TravelPlacePriceOutcome]:
    if not path.exists():
        return {}
    outcomes: dict[str, TravelPlacePriceOutcome] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            outcome = TravelPlacePriceOutcome.model_validate_json(line)
        except (ValueError, json.JSONDecodeError):
            continue
        outcomes[outcome.entity_id] = outcome
    return outcomes


def append_cache(path: Path, outcomes: list[TravelPlacePriceOutcome]) -> None:
    if not outcomes:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(outcome.model_dump_json(by_alias=True) + "\n")


async def fetch_outcomes(
    records: list[CandidateRecord],
    *,
    llm_client: GeminiLLMClient,
    model_name: str,
    concurrency: int,
    search_provider: WebSearchProvider | None = None,
    on_outcome: Callable[[TravelPlacePriceOutcome], None] | None = None,
) -> list[TravelPlacePriceOutcome]:
    queue: asyncio.Queue[CandidateRecord] = asyncio.Queue()
    for record in records:
        queue.put_nowait(record)
    quota_limited = asyncio.Event()
    outcomes: list[TravelPlacePriceOutcome] = []

    async def worker() -> None:
        while not quota_limited.is_set():
            try:
                record = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            outcome = (
                await research_travel_place_price_with_web_search(
                    record.candidate,
                    search_provider=search_provider,
                    llm_client=llm_client,
                    model_name=model_name,
                )
                if search_provider is not None
                else await research_travel_place_price(
                    record.candidate,
                    llm_client=llm_client,
                    model_name=model_name,
                )
            )
            outcomes.append(outcome)
            if on_outcome is not None:
                on_outcome(outcome)
            if outcome.error == "gemini_quota_limited":
                quota_limited.set()
            queue.task_done()

    worker_count = min(max(1, concurrency), 4, len(records))
    if worker_count:
        await asyncio.gather(*(worker() for _ in range(worker_count)))
    return outcomes


def is_terminal_cached_outcome(outcome: TravelPlacePriceOutcome) -> bool:
    if outcome.status in {
        PriceResearchStatus.verified_price,
        PriceResearchStatus.verified_free,
    }:
        return outcome.can_apply
    return outcome.status in TERMINAL_CACHE_STATUSES


def count_admission_prices(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(KnowledgeProperty)
            .where(KnowledgeProperty.key == "admission_price")
        )
        or 0
    )


def apply_outcomes(
    session: Session,
    outcomes: list[TravelPlacePriceOutcome],
    *,
    apply: bool,
    overwrite: bool,
) -> Counter[str]:
    stats: Counter[str] = Counter()
    repo = KnowledgeGraphRepository(session)
    for outcome in outcomes:
        if (
            outcome.status
            in {
                PriceResearchStatus.verified_price,
                PriceResearchStatus.verified_free,
            }
            and not outcome.has_grounded_source
        ):
            stats["missing_grounded_source_skipped"] += 1
            continue
        if not outcome.can_apply:
            continue
        existing = {
            prop.key: prop
            for prop in repo.get_properties_for_entity(outcome.entity_id)
            if prop.key == "admission_price"
        }
        if existing and not overwrite:
            stats["existing_price_skipped"] += 1
            continue
        primary_source = outcome.sources[0].uri if outcome.sources else None
        price_property = repo.upsert_property(
            outcome.entity_id,
            "admission_price",
            outcome.property_payload(),
            source=primary_source,
        )
        price_property.note = f"gemini_grounded_price_research:{outcome.model}"
        stats["admission_price_upserted"] += 1
    session.flush()
    if apply:
        session.commit()
    else:
        session.rollback()
    return stats


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    if not 1 <= args.concurrency <= 4:
        raise SystemExit("--concurrency must be between 1 and 4")
    if not 0 <= args.min_interval_seconds <= 60:
        raise SystemExit("--min-interval-seconds must be between 0 and 60")
    if args.min_review_count < 0:
        raise SystemExit("--min-review-count cannot be negative")
    if not settings.gemini_price_key_pool:
        raise SystemExit(
            "GEMINI_PRICE_API_KEYS or GEMINI_API_KEY is missing from backend/.env"
        )
    if args.search_provider == "tavily" and not settings.tavily_api_key:
        raise SystemExit(
            "TAVILY_API_KEY is required when --search-provider=tavily"
        )

    session = SessionLocal()
    aggregate: Counter[str] = Counter()
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
        llm_client = GeminiLLMClient(
            settings.gemini_price_key_pool,
            args.model,
            min_interval_seconds=args.min_interval_seconds,
        )
        if args.search_provider == "google_selenium":
            from app.integrations.search.google_selenium import (
                GoogleSeleniumSearchProvider,
            )

            web_search_provider: WebSearchProvider | None = (
                GoogleSeleniumSearchProvider(
                    timeout_seconds=settings.google_web_search_timeout_seconds,
                    min_interval_seconds=(
                        settings.google_web_search_min_interval_seconds
                    ),
                    page_load_wait_seconds=(
                        settings.google_selenium_page_load_wait_seconds
                    ),
                    post_search_delay_seconds=(
                        settings.google_selenium_post_search_delay_seconds
                    ),
                )
            )
        elif args.search_provider == "tavily":
            from app.integrations.search.tavily import TavilySearchProvider

            web_search_provider = TavilySearchProvider(
                settings.tavily_api_key or "",
                timeout_seconds=settings.tavily_timeout_seconds,
            )
        else:
            web_search_provider = None
        effective_concurrency = (
            1 if web_search_provider is not None else args.concurrency
        )
        aggregate["effective_concurrency"] = effective_concurrency

        def persist_outcome(outcome: TravelPlacePriceOutcome) -> None:
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
                concurrency=effective_concurrency,
                search_provider=web_search_provider,
                on_outcome=persist_outcome,
            )
        )
        quota_deferred = len(pending) - len(outcomes)
        if quota_deferred > 0 and any(
            outcome.error == "gemini_quota_limited"
            for outcome in outcomes
        ):
            aggregate["quota_limited_deferred"] += quota_deferred
        aggregate["admission_price_in_database"] = count_admission_prices(
            session
        )
    finally:
        session.close()

    print(
        json.dumps(
            {
                "status": "applied" if args.apply else "dry_run",
                "cacheFile": str(args.cache_file),
                "searchProvider": args.search_provider,
                **dict(sorted(aggregate.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
