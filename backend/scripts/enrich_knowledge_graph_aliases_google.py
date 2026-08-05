"""Learn Vietnamese Knowledge Graph aliases from exact Google Maps identities.

The existing place catalog contains stable Google identity URLs collected in an
English locale. This command opens those exact URLs in the project's Vietnamese
Google Maps worker and accepts a localized title only when the returned
``place_id`` or Google ``data_id`` is identical to the catalog record.

The command is resumable through a JSONL cache and defaults to dry-run. It never
accepts a fuzzy search result, category, address, or description as an alias.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.modules.knowledge_graph.model import (  # noqa: E402
    KnowledgeAlias,
    KnowledgeEntity,
)
from app.modules.knowledge_graph.text import (  # noqa: E402
    latin_transliteration,
    normalize_knowledge_text,
)
from app.modules.places.model import Place  # noqa: E402
from app.modules.places.resolver import (  # noqa: E402
    GoogleMapsScraperPlaceResolver,
)


TARGET_TYPES = ("TravelPlace", "Restaurant", "DrinkDessert", "Accommodation")
VENUE_PREFIXES = {
    "TravelPlace": "travel_place_",
    "Restaurant": "restaurant_",
    "DrinkDessert": "drink_dessert_",
    "Accommodation": "accommodation_",
}
GOOGLE_SOURCE = "google_maps_locale_vi"
TRANSLITERATION_SOURCE = "rule:google-maps-locale-vi-transliteration:v1"
DATA_ID_PATTERN = re.compile(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", re.IGNORECASE)


@dataclass(frozen=True)
class GoogleCandidate:
    entity_id: str
    entity_type: str
    canonical_name: str
    place_id: str
    source_link: str
    expected_data_id: str
    review_count: int


@dataclass(frozen=True)
class GoogleOutcome:
    entity_id: str
    place_id: str
    expected_data_id: str
    outcome: str
    title: str | None = None
    source_link: str | None = None
    fetched_at: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("var/google-maps-scraper"),
    )
    parser.add_argument(
        "--cache-file",
        type=Path,
        default=Path("var/knowledge-alias-google-vi-v1.jsonl"),
    )
    return parser.parse_args()


def google_data_id(source_link: str | None) -> str | None:
    if not source_link:
        return None
    match = DATA_ID_PATTERN.search(source_link)
    return match.group(1).casefold() if match else None


def has_vietnamese_diacritic(value: str) -> bool:
    if any(character in "Đđ" for character in value):
        return True
    return any(
        unicodedata.combining(character)
        for character in unicodedata.normalize("NFD", value)
    )


def exact_google_result(
    candidate: GoogleCandidate,
    results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    expected_data_id = candidate.expected_data_id.casefold()
    expected_place_id = candidate.place_id.casefold()
    for result in results:
        result_place_id = str(result.get("place_id") or "").casefold()
        result_data_id = str(result.get("data_id") or "").casefold()
        result_link_data_id = google_data_id(str(result.get("link") or ""))
        if result_place_id == expected_place_id or expected_data_id in {
            result_data_id,
            result_link_data_id,
        }:
            return result
    return None


def _place_id_for_entity(entity: KnowledgeEntity) -> str | None:
    prefix = VENUE_PREFIXES.get(entity.entity_type)
    if prefix is None or not entity.id.startswith(prefix):
        return None
    return entity.id[len(prefix) :]


def load_candidates(session: Session) -> list[GoogleCandidate]:
    entities = list(
        session.scalars(
            select(KnowledgeEntity).where(
                KnowledgeEntity.entity_type.in_(TARGET_TYPES)
            )
        )
    )
    entity_ids = [entity.id for entity in entities]
    aliases_by_entity: dict[str, list[str]] = defaultdict(list)
    for entity_id, alias in session.execute(
        select(KnowledgeAlias.entity_id, KnowledgeAlias.alias).where(
            KnowledgeAlias.entity_id.in_(entity_ids)
        )
    ):
        aliases_by_entity[entity_id].append(alias)

    place_ids = [
        place_id
        for entity in entities
        if (place_id := _place_id_for_entity(entity)) is not None
    ]
    places = {
        place.id: place
        for place in session.scalars(select(Place).where(Place.id.in_(place_ids)))
    }

    candidates: list[GoogleCandidate] = []
    for entity in entities:
        if has_vietnamese_diacritic(entity.canonical_name) or any(
            has_vietnamese_diacritic(alias)
            for alias in aliases_by_entity[entity.id]
        ):
            continue
        place_id = _place_id_for_entity(entity)
        place = places.get(place_id or "")
        expected_data_id = google_data_id(place.source_link if place else None)
        if place is None or not place.source_link or not expected_data_id:
            continue
        candidates.append(
            GoogleCandidate(
                entity_id=entity.id,
                entity_type=entity.entity_type,
                canonical_name=entity.canonical_name,
                place_id=place.id,
                source_link=place.source_link,
                expected_data_id=expected_data_id,
                review_count=place.review_count or 0,
            )
        )
    return sorted(
        candidates,
        key=lambda candidate: (-candidate.review_count, candidate.entity_id),
    )


def load_cache(cache_file: Path) -> dict[str, GoogleOutcome]:
    if not cache_file.exists():
        return {}
    outcomes: dict[str, GoogleOutcome] = {}
    for line in cache_file.read_text(encoding="utf-8").splitlines():
        try:
            value = GoogleOutcome(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        outcomes[value.entity_id] = value
    return outcomes


def append_cache(cache_file: Path, outcomes: list[GoogleOutcome]) -> None:
    if not outcomes:
        return
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    with cache_file.open("a", encoding="utf-8") as handle:
        for outcome in outcomes:
            handle.write(json.dumps(asdict(outcome), ensure_ascii=False) + "\n")


async def fetch_outcomes(
    candidates: list[GoogleCandidate],
    *,
    resolver: GoogleMapsScraperPlaceResolver,
    concurrency: int,
) -> list[GoogleOutcome]:
    semaphore = asyncio.Semaphore(max(1, min(concurrency, 4)))

    async def fetch(candidate: GoogleCandidate) -> GoogleOutcome:
        async with semaphore:
            fetched_at = datetime.now(timezone.utc).isoformat()
            try:
                batch = await resolver._search([candidate.source_link])
            except (OSError, RuntimeError, TypeError, ValueError, asyncio.TimeoutError):
                return GoogleOutcome(
                    candidate.entity_id,
                    candidate.place_id,
                    candidate.expected_data_id,
                    "provider_error",
                    fetched_at=fetched_at,
                )
            result = exact_google_result(candidate, list(batch.results))
            if result is None:
                return GoogleOutcome(
                    candidate.entity_id,
                    candidate.place_id,
                    candidate.expected_data_id,
                    "identity_mismatch",
                    fetched_at=fetched_at,
                )
            title = " ".join(str(result.get("title") or "").split())[:255]
            if not title or not has_vietnamese_diacritic(title):
                return GoogleOutcome(
                    candidate.entity_id,
                    candidate.place_id,
                    candidate.expected_data_id,
                    "no_vietnamese_title",
                    title=title or None,
                    source_link=str(result.get("link") or candidate.source_link),
                    fetched_at=fetched_at,
                )
            return GoogleOutcome(
                candidate.entity_id,
                candidate.place_id,
                candidate.expected_data_id,
                "verified",
                title=title,
                source_link=str(result.get("link") or candidate.source_link),
                fetched_at=fetched_at,
            )

    return list(await asyncio.gather(*(fetch(candidate) for candidate in candidates)))


def apply_outcomes(
    session: Session,
    outcomes: list[GoogleOutcome],
    *,
    apply: bool,
) -> Counter[str]:
    stats: Counter[str] = Counter()
    verified = [outcome for outcome in outcomes if outcome.outcome == "verified"]
    if not verified:
        return stats
    aliases_by_entity: dict[str, list[KnowledgeAlias]] = defaultdict(list)
    for alias in session.scalars(
        select(KnowledgeAlias).where(
            KnowledgeAlias.entity_id.in_(
                [outcome.entity_id for outcome in verified]
            )
        )
    ):
        aliases_by_entity[alias.entity_id].append(alias)

    for outcome in verified:
        if not outcome.title:
            continue
        existing = aliases_by_entity[outcome.entity_id]
        existing_values = {alias.alias.casefold() for alias in existing}
        created_for_entity = 0
        verified_at = (
            datetime.fromisoformat(outcome.fetched_at)
            if outcome.fetched_at
            else datetime.now(timezone.utc)
        )
        if outcome.title.casefold() not in existing_values and len(existing) < 32:
            session.add(
                KnowledgeAlias(
                    entity_id=outcome.entity_id,
                    alias=outcome.title,
                    normalized_alias=normalize_knowledge_text(outcome.title),
                    language="vi",
                    alias_type="alternate_name",
                    source=outcome.source_link,
                    provider=GOOGLE_SOURCE,
                    status="verified",
                    confidence=1.0,
                    verified_at=verified_at,
                )
            )
            existing_values.add(outcome.title.casefold())
            created_for_entity += 1
            stats["vietnamese_aliases_created"] += 1
        transliteration = latin_transliteration(outcome.title)
        if (
            transliteration
            and any("a" <= char <= "z" for char in transliteration.casefold())
            and transliteration.casefold() != outcome.title.casefold()
            and transliteration.casefold() not in existing_values
            and len(existing) + created_for_entity < 32
        ):
            session.add(
                KnowledgeAlias(
                    entity_id=outcome.entity_id,
                    alias=transliteration,
                    normalized_alias=normalize_knowledge_text(transliteration),
                    language="vi-Latn",
                    alias_type="transliteration",
                    source=TRANSLITERATION_SOURCE,
                    provider=GOOGLE_SOURCE,
                    status="generated",
                    confidence=0.99,
                    verified_at=verified_at,
                )
            )
            created_for_entity += 1
            stats["transliterations_created"] += 1
        stats["verified_titles"] += 1

    session.flush()
    if apply:
        session.commit()
    else:
        session.rollback()
    return stats


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.batch_size < 1:
        raise SystemExit("--limit and --batch-size must be positive")
    session = SessionLocal()
    aggregate: Counter[str] = Counter()
    try:
        candidates = load_candidates(session)
        cache = load_cache(args.cache_file)
        aggregate["eligible_before_cache"] = len(candidates)

        cached_verified = [
            cache[candidate.entity_id]
            for candidate in candidates
            if candidate.entity_id in cache
            and cache[candidate.entity_id].outcome == "verified"
        ]
        if cached_verified:
            aggregate.update(
                apply_outcomes(session, cached_verified, apply=args.apply)
            )

        pending = [
            candidate
            for candidate in candidates
            if candidate.entity_id not in cache
        ][: args.limit]
        resolver = GoogleMapsScraperPlaceResolver(
            work_dir=args.work_dir,
            timeout_seconds=args.timeout_seconds,
            max_alias_queries=1,
            max_concurrency=args.concurrency,
        )
        for start in range(0, len(pending), args.batch_size):
            batch_candidates = pending[start : start + args.batch_size]
            outcomes = asyncio.run(
                fetch_outcomes(
                    batch_candidates,
                    resolver=resolver,
                    concurrency=args.concurrency,
                )
            )
            if args.apply:
                append_cache(args.cache_file, outcomes)
            aggregate["google_queries"] += len(outcomes)
            aggregate.update(outcome.outcome for outcome in outcomes)
            aggregate.update(apply_outcomes(session, outcomes, apply=args.apply))
            print(
                json.dumps(
                    {
                        "processed": min(start + len(batch_candidates), len(pending)),
                        "scheduled": len(pending),
                        **dict(sorted(aggregate.items())),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    finally:
        session.close()
    print(
        json.dumps(
            {
                "status": "applied" if args.apply else "dry_run",
                **dict(sorted(aggregate.items())),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
