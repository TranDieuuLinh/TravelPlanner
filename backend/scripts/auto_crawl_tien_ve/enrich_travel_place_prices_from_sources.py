"""Extract sourced adult admission prices from provided web source snippets.

Input JSONL rows must include an entity ID and one or more public HTTP(S)
sources. The command asks Gemini to verify the adult standard daytime admission
price from only those provided source snippets, then optionally writes verified
results to ``knowledge_properties.admission_price``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import and_, select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.integrations.llm.provider import GeminiLLMClient  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.price_research import (  # noqa: E402
    TravelPlacePriceCandidate,
    TravelPlacePriceOutcome,
    research_travel_place_price_from_sources,
)
from scripts.auto_crawl_tien_ve.enrich_travel_place_prices import (  # noqa: E402
    RESEARCH_PROPERTY_KEYS,
    append_cache,
    apply_outcomes,
    count_admission_prices,
)


@dataclass(frozen=True)
class SourceInputRecord:
    candidate: TravelPlacePriceCandidate
    sources: list[dict[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sources-file",
        type=Path,
        required=True,
        help=(
            "JSONL file. Each line: "
            '{"entityId":"...","sources":[{"title":"...","uri":"...","snippet":"..."}]}'
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit verified prices; default only researches and caches results.",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument(
        "--min-interval-seconds",
        type=float,
        default=settings.gemini_price_min_interval_seconds,
        help="Minimum delay between Gemini request starts.",
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=Path("var/travel-place-price-source-extraction-v1.jsonl"),
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


def _row_entity_id(row: dict) -> str:
    return str(row.get("entityId") or row.get("entity_id") or "").strip()


def _row_sources(row: dict) -> list[dict[str, str]]:
    raw_sources = row.get("sources")
    if not isinstance(raw_sources, list):
        return []
    sources: list[dict[str, str]] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        sources.append(
            {
                "title": str(source.get("title") or "").strip(),
                "uri": str(source.get("uri") or source.get("url") or "").strip(),
                "snippet": str(
                    source.get("snippet") or source.get("content") or ""
                ).strip(),
            }
        )
    return sources


def load_source_rows(path: Path) -> dict[str, list[dict[str, str]]]:
    if not path.exists():
        raise SystemExit(f"--sources-file does not exist: {path}")
    rows: dict[str, list[dict[str, str]]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid JSON on line {line_number}: {exc}") from exc
        if not isinstance(raw, dict):
            raise SystemExit(f"Line {line_number} must be a JSON object.")
        entity_id = _row_entity_id(raw)
        if not entity_id:
            raise SystemExit(f"Line {line_number} is missing entityId.")
        sources = _row_sources(raw)
        if not sources:
            raise SystemExit(f"Line {line_number} is missing sources.")
        rows.setdefault(entity_id, []).extend(sources)
    return rows


def load_records(
    session: Session,
    source_rows: dict[str, list[dict[str, str]]],
    *,
    overwrite: bool,
) -> list[SourceInputRecord]:
    rows = session.execute(
        select(KnowledgeEntity, KnowledgeProperty)
        .outerjoin(
            KnowledgeProperty,
            and_(
                KnowledgeProperty.entity_id == KnowledgeEntity.id,
                KnowledgeProperty.key.in_(RESEARCH_PROPERTY_KEYS),
            ),
        )
        .where(KnowledgeEntity.id.in_(source_rows))
        .where(KnowledgeEntity.entity_type == "TravelPlace")
        .order_by(KnowledgeEntity.id)
    )
    entities: dict[str, KnowledgeEntity] = {}
    properties: dict[str, dict[str, str]] = {}
    for entity, prop in rows:
        entities[entity.id] = entity
        properties.setdefault(entity.id, {})
        if prop is not None:
            properties[entity.id][prop.key] = prop.value

    records: list[SourceInputRecord] = []
    for entity_id, entity in entities.items():
        props = properties.get(entity_id, {})
        if props.get("admission_price") and not overwrite:
            continue
        try:
            review_count = max(0, int(float(props.get("review_count", "0") or 0)))
        except ValueError:
            review_count = 0
        records.append(
            SourceInputRecord(
                candidate=TravelPlacePriceCandidate(
                    entityId=entity.id,
                    canonicalName=entity.canonical_name,
                    address=props.get("address") or None,
                    city=props.get("city") or None,
                    country=props.get("country") or None,
                    placeType=props.get("place_type") or None,
                    sourceUrl=props.get("source_url") or None,
                    reviewCount=review_count,
                ),
                sources=source_rows[entity_id],
            )
        )
    return records


async def fetch_source_outcomes(
    records: list[SourceInputRecord],
    *,
    llm_client: GeminiLLMClient,
    model_name: str,
    concurrency: int,
    on_outcome: Callable[[TravelPlacePriceOutcome], None] | None = None,
) -> list[TravelPlacePriceOutcome]:
    queue: asyncio.Queue[SourceInputRecord] = asyncio.Queue()
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
            outcome = await research_travel_place_price_from_sources(
                record.candidate,
                sources=record.sources,
                llm_client=llm_client,
                model_name=model_name,
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


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be positive")
    if not 1 <= args.concurrency <= 4:
        raise SystemExit("--concurrency must be between 1 and 4")
    if not 0 <= args.min_interval_seconds <= 60:
        raise SystemExit("--min-interval-seconds must be between 0 and 60")
    if not settings.gemini_price_key_pool:
        raise SystemExit(
            "GEMINI_PRICE_API_KEYS or GEMINI_API_KEY is missing from backend/.env"
        )

    source_rows = load_source_rows(args.sources_file)
    session = SessionLocal()
    aggregate: Counter[str] = Counter()
    try:
        records = load_records(session, source_rows, overwrite=args.overwrite)
        aggregate["input_entities"] = len(source_rows)
        aggregate["eligible"] = len(records)
        pending = records[: args.limit]
        aggregate["scheduled"] = len(pending)
        llm_client = GeminiLLMClient(
            settings.gemini_price_key_pool,
            args.model,
            min_interval_seconds=args.min_interval_seconds,
        )

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
            fetch_source_outcomes(
                pending,
                llm_client=llm_client,
                model_name=args.model,
                concurrency=args.concurrency,
                on_outcome=persist_outcome,
            )
        )
        quota_deferred = len(pending) - len(outcomes)
        if quota_deferred > 0 and any(
            outcome.error == "gemini_quota_limited" for outcome in outcomes
        ):
            aggregate["quota_limited_deferred"] += quota_deferred
        aggregate["admission_price_in_database"] = count_admission_prices(session)
    finally:
        session.close()

    print(
        json.dumps(
            {
                "status": "applied" if args.apply else "dry_run",
                "cacheFile": str(args.cache_file),
                "sourcesFile": str(args.sources_file),
                **dict(sorted(aggregate.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
