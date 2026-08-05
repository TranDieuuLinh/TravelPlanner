"""Repair graph names and enrich aliases from already-verified place data.

The command is resumable and idempotent. It never invents an English name,
former name, abbreviation, or nickname. Provider names and aliases are copied
with provenance; deterministic Latin spellings are marked as generated.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

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
    repair_cp437_utf8_mojibake,
)
from app.modules.places.model import Place  # noqa: E402


TARGET_TYPES = (
    "Area",
    "TravelPlace",
    "Restaurant",
    "DrinkDessert",
    "Accommodation",
)
VENUE_PREFIXES = {
    "TravelPlace": "travel_place_",
    "Restaurant": "restaurant_",
    "DrinkDessert": "drink_dessert_",
    "Accommodation": "accommodation_",
}
ALIAS_LIMIT_PER_ENTITY = 32
RULE_SOURCE = "rule:knowledge-alias-enrichment:v1"
LEGACY_SOURCE = "database/kg_dump_v7.sql"


@dataclass(frozen=True)
class AliasCandidate:
    value: str
    language: str
    alias_type: str
    source: str
    provider: str | None
    status: str
    confidence: float
    verified_at: datetime | None = None


AREA_CURATED_ALIASES: dict[str, tuple[AliasCandidate, ...]] = {
    "ha noi": (
        AliasCandidate("Hanoi", "en", "english_name", "curation:area-aliases:v1", None, "curated", 1.0),
        AliasCandidate("HN", "und", "abbreviation", "curation:area-aliases:v1", None, "curated", 0.95),
    ),
    "ho chi minh": (
        AliasCandidate("Ho Chi Minh City", "en", "english_name", "curation:area-aliases:v1", None, "curated", 1.0),
        AliasCandidate("HCMC", "en", "abbreviation", "curation:area-aliases:v1", None, "curated", 1.0),
        AliasCandidate("HCM", "und", "abbreviation", "curation:area-aliases:v1", None, "curated", 0.9),
        AliasCandidate("TP HCM", "vi", "abbreviation", "curation:area-aliases:v1", None, "curated", 1.0),
        AliasCandidate("Sài Gòn", "vi", "former_name", "curation:area-aliases:v1", None, "curated", 1.0),
        AliasCandidate("Saigon", "en", "former_name", "curation:area-aliases:v1", None, "curated", 1.0),
    ),
    "viet nam": (
        AliasCandidate("Vietnam", "en", "english_name", "curation:area-aliases:v1", None, "curated", 1.0),
        AliasCandidate("VN", "und", "abbreviation", "curation:area-aliases:v1", None, "curated", 1.0),
    ),
    "da nang": (
        AliasCandidate("Danang", "en", "english_name", "curation:area-aliases:v1", None, "curated", 0.95),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Commit changes; default is dry-run.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--start-after", default=None)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def place_id_for_entity(entity: KnowledgeEntity) -> str | None:
    prefix = VENUE_PREFIXES.get(entity.entity_type)
    if prefix is None or not entity.id.startswith(prefix):
        return None
    return entity.id[len(prefix):]


def canonical_name_for_entity(
    entity: KnowledgeEntity,
    place: Place | None,
) -> tuple[str, str, str | None, datetime | None]:
    if place is not None and place.name.strip():
        return (
            " ".join(place.name.split()),
            place.source_link or f"places:{place.id}",
            place.source_platform,
            place.source_fetched_at,
        )
    repaired = repair_cp437_utf8_mojibake(entity.canonical_name)
    return repaired, "repair:cp437-utf8:v1", None, None


def candidates_for_entity(
    entity: KnowledgeEntity,
    canonical_name: str,
    *,
    place: Place | None,
    linked_verified_place: Place | None = None,
) -> list[AliasCandidate]:
    candidates: list[AliasCandidate] = []
    latin_name = latin_transliteration(canonical_name)
    if (
        _is_searchable_latin(latin_name)
        and latin_name.casefold() != canonical_name.casefold()
    ):
        candidates.append(
            AliasCandidate(
                latin_name,
                "vi-Latn",
                "transliteration",
                RULE_SOURCE,
                None,
                "generated",
                0.98,
            )
        )

    if entity.entity_type == "Area":
        candidates.extend(
            AREA_CURATED_ALIASES.get(normalize_knowledge_text(canonical_name), ())
        )

    if place is not None:
        source = place.source_link or f"places:{place.id}"
        provider = place.source_platform
        for fragment in provider_name_fragments(canonical_name):
            candidates.append(
                AliasCandidate(
                    fragment,
                    "und",
                    "former_name",
                    source,
                    provider,
                    "verified",
                    _place_confidence(place),
                    place.source_fetched_at,
                )
            )
        candidates.extend(_metadata_aliases(place))

    if linked_verified_place is not None:
        linked_name = " ".join(linked_verified_place.name.split())
        if normalize_knowledge_text(linked_name) != normalize_knowledge_text(
            canonical_name
        ):
            candidates.append(
                AliasCandidate(
                    linked_name,
                    _alias_language(linked_name),
                    "alternate_name",
                    linked_verified_place.source_link
                    or f"places:{linked_verified_place.id}",
                    linked_verified_place.source_platform,
                    "verified",
                    _place_confidence(linked_verified_place),
                    linked_verified_place.source_fetched_at,
                )
            )
        candidates.extend(_metadata_aliases(linked_verified_place))

    return _deduplicate_candidates(candidates)


def provider_name_fragments(value: str) -> list[str]:
    """Extract only former names explicitly labelled by the provider.

    Pipe-separated Google labels commonly contain services, addresses, SEO
    phrases, or categories rather than names. Those fragments are deliberately
    ignored unless a provider supplies structured ``verifiedAliases`` metadata.
    """
    fragments: list[str] = []
    former_patterns = (
        r"\bformerly\s+(.+)$",
        r"\bpreviously\s+(.+)$",
        r"\btrước đây(?: là)?\s+(.+)$",
    )
    for pattern in former_patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            fragments.append(match.group(1).strip(" -|()"))
    return [
        fragment
        for fragment in dict.fromkeys(fragments)
        if 2 <= len(fragment) <= 255 and fragment.casefold() != value.casefold()
    ]


def classify_existing_alias(alias: str, canonical_name: str) -> tuple[str, str]:
    if (
        alias.isascii()
        and not canonical_name.isascii()
        and normalize_knowledge_text(alias) == normalize_knowledge_text(canonical_name)
    ):
        return "transliteration", "vi-Latn"
    return "alternate_name", "und"


def enrich_batch(
    session: Session,
    entities: list[KnowledgeEntity],
    *,
    apply: bool,
) -> Counter[str]:
    stats: Counter[str] = Counter()
    place_ids = [
        place_id
        for entity in entities
        if (place_id := place_id_for_entity(entity)) is not None
    ]
    places = {
        place.id: place
        for place in session.scalars(select(Place).where(Place.id.in_(place_ids)))
    }
    verified_alias_sources = list(
        session.scalars(
            select(Place).where(Place.source_platform == "google_maps_scraper")
        )
    )
    aliases_by_entity: dict[str, list[KnowledgeAlias]] = defaultdict(list)
    for alias in session.scalars(
        select(KnowledgeAlias).where(
            KnowledgeAlias.entity_id.in_([entity.id for entity in entities])
        )
    ):
        aliases_by_entity[alias.entity_id].append(alias)

    for entity in entities:
        place_id = place_id_for_entity(entity)
        place = places.get(place_id) if place_id else None
        linked_verified_place = _linked_verified_place(
            place, verified_alias_sources
        )
        canonical_name, canonical_source, _canonical_provider, _verified_at = (
            canonical_name_for_entity(entity, place)
        )
        normalized_name = normalize_knowledge_text(canonical_name)
        if (
            canonical_name != entity.canonical_name
            or normalized_name != entity.normalized_name
        ):
            entity.canonical_name = canonical_name
            entity.normalized_name = normalized_name
            entity.updated_at = datetime.now(timezone.utc)
            stats["entities_repaired"] += 1

        existing_aliases = aliases_by_entity[entity.id]
        invalid_generated_aliases = [
            alias
            for alias in existing_aliases
            if alias.source == RULE_SOURCE
            and alias.alias_type == "transliteration"
            and not _is_searchable_latin(alias.alias)
        ]
        for alias in invalid_generated_aliases:
            session.delete(alias)
            stats["aliases_removed_invalid"] += 1
        existing_aliases = [
            alias
            for alias in existing_aliases
            if alias not in invalid_generated_aliases
        ]
        existing_values = {alias.alias.casefold() for alias in existing_aliases}
        for alias in existing_aliases:
            repaired_alias = repair_cp437_utf8_mojibake(alias.alias)
            if (
                repaired_alias != alias.alias
                and repaired_alias.casefold() not in existing_values
            ):
                existing_values.discard(alias.alias.casefold())
                alias.alias = repaired_alias
                alias.normalized_alias = normalize_knowledge_text(repaired_alias)
                existing_values.add(repaired_alias.casefold())
                stats["aliases_repaired"] += 1
            if (
                alias.source is None
                or alias.source == LEGACY_SOURCE
            ):
                alias_type, language = classify_existing_alias(
                    alias.alias, canonical_name
                )
                alias.alias_type = alias_type
                alias.language = language
                alias.source = alias.source or LEGACY_SOURCE
                alias.provider = alias.provider or "legacy_import"
                alias.status = alias.status or "imported"
                alias.confidence = alias.confidence or 0.7
                stats["aliases_classified"] += 1

        available_slots = max(0, ALIAS_LIMIT_PER_ENTITY - len(existing_aliases))
        existing_by_value = {
            alias.alias.casefold(): alias for alias in existing_aliases
        }
        for candidate in candidates_for_entity(
            entity,
            canonical_name,
            place=place,
            linked_verified_place=linked_verified_place,
        ):
            alias_value = " ".join(candidate.value.split())[:255]
            if (
                not alias_value
                or alias_value.casefold() == canonical_name.casefold()
            ):
                continue
            existing_alias = existing_by_value.get(alias_value.casefold())
            candidate_source = candidate.source or canonical_source
            if existing_alias is not None:
                if (
                    existing_alias.source == candidate_source
                    or _evidence_rank(candidate.status)
                    > _evidence_rank(existing_alias.status)
                ):
                    candidate_metadata = (
                        normalize_knowledge_text(alias_value),
                        candidate.language,
                        candidate.alias_type,
                        candidate_source,
                        candidate.provider,
                        candidate.status,
                        candidate.confidence,
                        candidate.verified_at,
                    )
                    existing_metadata = (
                        existing_alias.normalized_alias,
                        existing_alias.language,
                        existing_alias.alias_type,
                        existing_alias.source,
                        existing_alias.provider,
                        existing_alias.status,
                        existing_alias.confidence,
                        existing_alias.verified_at,
                    )
                    if candidate_metadata != existing_metadata:
                        (
                            existing_alias.normalized_alias,
                            existing_alias.language,
                            existing_alias.alias_type,
                            existing_alias.source,
                            existing_alias.provider,
                            existing_alias.status,
                            existing_alias.confidence,
                            existing_alias.verified_at,
                        ) = candidate_metadata
                        stats["aliases_refreshed"] += 1
                continue
            if available_slots < 1:
                continue
            session.add(
                KnowledgeAlias(
                    entity_id=entity.id,
                    alias=alias_value,
                    normalized_alias=normalize_knowledge_text(alias_value),
                    language=candidate.language,
                    alias_type=candidate.alias_type,
                    source=candidate_source,
                    provider=candidate.provider,
                    status=candidate.status,
                    confidence=candidate.confidence,
                    verified_at=candidate.verified_at,
                )
            )
            existing_values.add(alias_value.casefold())
            available_slots -= 1
            stats["aliases_created"] += 1
            stats[f"created_type:{candidate.alias_type}"] += 1
        stats["entities_processed"] += 1

    session.flush()
    if apply:
        session.commit()
    else:
        session.rollback()
    return stats


def _is_searchable_latin(value: str) -> bool:
    normalized = normalize_knowledge_text(value)
    return any("a" <= character <= "z" for character in normalized)


def _evidence_rank(status: str | None) -> int:
    return {
        "imported": 1,
        "generated": 1,
        "provider_observed": 2,
        "curated": 3,
        "verified": 4,
    }.get(status or "", 0)


def _metadata_aliases(place: Place) -> list[AliasCandidate]:
    metadata = place.metadata_json if isinstance(place.metadata_json, dict) else {}
    source = place.source_link or f"places:{place.id}"
    provider = place.source_platform
    verified_at = place.source_fetched_at
    candidates: list[AliasCandidate] = []
    verified_by_name = {
        str(item.get("name", "")).casefold(): item
        for item in metadata.get("verifiedAliases", [])
        if isinstance(item, dict) and item.get("name")
    }
    for raw_alias in metadata.get("aliases", []):
        if not isinstance(raw_alias, str):
            continue
        verified = verified_by_name.get(raw_alias.casefold(), {})
        candidates.append(
            AliasCandidate(
                raw_alias,
                str(verified.get("language") or "und")[:8],
                _metadata_alias_type(
                    raw_alias, str(verified.get("language") or "und")
                ),
                source,
                str(verified.get("provider") or provider or "") or None,
                "verified" if verified else "provider_observed",
                _place_confidence(place) if verified else 0.8,
                verified_at,
            )
        )
    return candidates


def _linked_verified_place(
    place: Place | None,
    verified_sources: list[Place],
) -> Place | None:
    if place is None or not place.source_link:
        return None
    return next(
        (
            source
            for source in verified_sources
            if source.id in place.source_link
            and isinstance(source.metadata_json, dict)
            and source.metadata_json.get("verifiedAliases")
        ),
        None,
    )


def _alias_language(value: str) -> str:
    vietnamese_markers = "ăâđêôơưĂÂĐÊÔƠƯ"
    if any(character in value for character in vietnamese_markers):
        return "vi"
    return "und"


def _metadata_alias_type(value: str, language: str) -> str:
    if language == "en" or re.search(
        r"\b(cathedral|church|lake|mausoleum|museum|pagoda|prison|temple)\b",
        value,
        flags=re.IGNORECASE,
    ):
        return "english_name"
    return "short_name"


def _place_confidence(place: Place) -> float:
    return {"high": 0.98, "medium": 0.9, "low": 0.75}.get(
        place.data_confidence, 0.8
    )


def _deduplicate_candidates(
    candidates: Iterable[AliasCandidate],
) -> list[AliasCandidate]:
    result: list[AliasCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = " ".join(candidate.value.split())
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def main() -> int:
    args = parse_args()
    if args.batch_size < 1 or args.batch_size > 5000:
        raise ValueError("batch-size must be between 1 and 5000")
    if args.limit is not None and args.limit < 1:
        raise ValueError("limit must be positive")

    totals: Counter[str] = Counter()
    last_id: str | None = args.start_after
    remaining = args.limit
    with SessionLocal() as session:
        if session.get_bind().dialect.name != "postgresql":
            raise RuntimeError("This enrichment command requires PostgreSQL")
        while remaining is None or remaining > 0:
            size = args.batch_size if remaining is None else min(args.batch_size, remaining)
            query = (
                select(KnowledgeEntity)
                .where(KnowledgeEntity.entity_type.in_(TARGET_TYPES))
                .order_by(KnowledgeEntity.id)
                .limit(size)
            )
            if last_id:
                query = query.where(KnowledgeEntity.id > last_id)
            entities = list(session.scalars(query))
            if not entities:
                break
            totals.update(enrich_batch(session, entities, apply=args.apply))
            last_id = entities[-1].id
            if remaining is not None:
                remaining -= len(entities)

    print(json.dumps({
        "status": "applied" if args.apply else "dry_run",
        "lastEntityId": last_id,
        "targetTypes": list(TARGET_TYPES),
        **dict(sorted(totals.items())),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
