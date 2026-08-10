"""Planner-facing projection of canonical Knowledge Graph places.

The public API still calls the identifier ``placeId`` for compatibility, but
records returned here use ``knowledge_entities.id`` as that identifier.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from typing import Any, Iterator

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.research.schema import PLACE_TYPES
from app.modules.knowledge_graph.text import (
    normalize_knowledge_text,
    repair_cp437_utf8_mojibake,
)
from app.modules.knowledge_graph.tag_model import KnowledgeEntityTagAssertion
from app.modules.places.auto_statistics.domain import PlaceStatisticsRecord
from app.modules.places.eligibility import place_record_is_search_eligible
from app.modules.places.model import KnowledgeEntityImage


SEARCHABLE_ALIAS_STATUSES = {"imported", "verified", "active", "approved"}
VERIFIED_ALIAS_STATUSES = {"verified", "active", "approved"}
PROJECTION_BATCH_SIZE = 1_000
PORTABLE_SIMILARITY_SCAN_LIMIT = 5_000
PORTABLE_RETRIEVAL_MINIMUM_SCORE = 0.30


@dataclass(frozen=True)
class KnowledgeGraphImage:
    image_url: str


@dataclass(frozen=True)
class KnowledgeGraphPlaceRecord:
    id: str
    name: str
    place_type: str
    address: str | None
    city: str | None
    country: str | None
    country_code: str | None
    primary_area: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    data_confidence: str
    region_key: str
    status: str
    opening_hours: list[dict]
    preferred_time_windows: list[dict]
    typical_duration_minutes: int | None
    source_platform: str | None
    source_link: str | None
    plus_code: str | None
    rating: Decimal | None
    review_count: int | None
    revision: int
    source_fetched_at: datetime | None
    metadata_json: dict[str, Any]
    images: list[KnowledgeGraphImage]
    deleted_at: None = None


class KnowledgeGraphPlaceRepository:
    """Read all Planner place data from canonical KG entities/properties."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, entity_id: str) -> KnowledgeGraphPlaceRecord | None:
        current_id = entity_id
        visited: set[str] = set()
        while current_id not in visited:
            visited.add(current_id)
            entity = self.session.scalar(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.id == current_id,
                    KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                )
            )
            records = self._project([entity] if entity is not None else [])
            if not records:
                return None
            record = records[0]
            if record.status != "merged":
                return record
            merged_into = self.session.scalar(
                select(KnowledgeProperty.value).where(
                    KnowledgeProperty.entity_id == current_id,
                    KnowledgeProperty.key == "merged_into_entity_id",
                )
            )
            if not merged_into:
                return None
            current_id = merged_into
        return None

    def list_for_place_selection(
        self, region_key: str, *, limit: int = 10000
    ) -> list[KnowledgeGraphPlaceRecord]:
        return self._list_by_region(region_key, limit=limit)

    def get_many(self, entity_ids: list[str]) -> list[KnowledgeGraphPlaceRecord]:
        """Project a bounded set of canonical Places without N+1 lookups."""
        ordered_ids = list(dict.fromkeys(entity_ids))
        if not ordered_ids:
            return []
        entities = list(
            self.session.scalars(
                select(KnowledgeEntity).where(
                    KnowledgeEntity.id.in_(ordered_ids),
                    KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                )
            )
        )
        projected = self._active(self._project(entities))
        by_id = {record.id: record for record in projected}
        return [by_id[entity_id] for entity_id in ordered_ids if entity_id in by_id]

    def list_active_for_planner_research(
        self, region_key: str | None = None, *, limit: int = 5000
    ) -> list[KnowledgeGraphPlaceRecord]:
        if region_key:
            return self._list_by_region(region_key, limit=limit)
        entities = list(
            self.session.scalars(
                select(KnowledgeEntity)
                .where(KnowledgeEntity.entity_type.in_(PLACE_TYPES))
                .order_by(KnowledgeEntity.id)
                .limit(limit)
            )
        )
        return self._active(self._project(entities))

    def search_active_by_names(
        self, names: list[str], *, limit: int = 100
    ) -> list[KnowledgeGraphPlaceRecord]:
        keys = list(dict.fromkeys(
            key
            for name in names
            if (key := normalize_knowledge_text(name))
        ))
        if not keys or limit < 1:
            return []

        if self.session.get_bind().dialect.name == "postgresql":
            entities = self._search_postgresql_by_similarity(keys, limit=limit)
        else:
            # Runtime is PostgreSQL-only. This bounded deterministic fallback
            # keeps isolated SQLite tests representative without requiring
            # PostgreSQL extension functions in the test process.
            entities = self._search_portable_by_similarity(keys, limit=limit)
        return self._active(self._project(entities))

    def _search_postgresql_by_similarity(
        self,
        keys: list[str],
        *,
        limit: int,
    ) -> list[KnowledgeEntity]:
        """Retrieve exact identities first, then trigram/word-similar rows.

        Migration 0035 installs ``pg_trgm`` plus GIN indexes for both
        normalized name columns. The indexed similarity operators form a
        broad shortlist; the resolver remains responsible for strict identity,
        region, source-address and branch-margin checks.
        """
        exact_predicates = [
            predicate
            for key in keys
            for predicate in (
                KnowledgeEntity.normalized_name == key,
                KnowledgeEntity.aliases.any(
                    and_(
                        KnowledgeAlias.normalized_alias == key,
                        KnowledgeAlias.status.in_(SEARCHABLE_ALIAS_STATUSES),
                    )
                ),
            )
        ]
        exact_entities = list(
            self.session.scalars(
                select(KnowledgeEntity)
                .where(
                    KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                    or_(*exact_predicates),
                )
                .order_by(KnowledgeEntity.id)
                .limit(limit)
            )
        )
        if exact_entities:
            return exact_entities

        predicates = []
        scores = []
        for key in keys:
            alias_exact = and_(
                KnowledgeAlias.normalized_alias == key,
                KnowledgeAlias.status.in_(SEARCHABLE_ALIAS_STATUSES),
            )
            alias_similar = and_(
                KnowledgeAlias.status.in_(SEARCHABLE_ALIAS_STATUSES),
                or_(
                    alias_exact,
                    KnowledgeAlias.normalized_alias.op("%")(key),
                    KnowledgeAlias.normalized_alias.op("%>")(key),
                ),
            )
            alias_score = (
                select(
                    func.max(
                        func.greatest(
                            case((alias_exact, 2.0), else_=0.0),
                            func.similarity(
                                KnowledgeAlias.normalized_alias,
                                key,
                            ),
                            func.word_similarity(
                                key,
                                KnowledgeAlias.normalized_alias,
                            ),
                        )
                    )
                )
                .where(
                    KnowledgeAlias.entity_id == KnowledgeEntity.id,
                    KnowledgeAlias.status.in_(SEARCHABLE_ALIAS_STATUSES),
                )
                .correlate(KnowledgeEntity)
                .scalar_subquery()
            )
            predicates.extend(
                [
                    KnowledgeEntity.normalized_name == key,
                    KnowledgeEntity.normalized_name.op("%")(key),
                    KnowledgeEntity.normalized_name.op("%>")(key),
                    KnowledgeEntity.aliases.any(alias_similar),
                ]
            )
            scores.append(
                func.greatest(
                    case(
                        (KnowledgeEntity.normalized_name == key, 2.0),
                        else_=0.0,
                    ),
                    func.similarity(KnowledgeEntity.normalized_name, key),
                    func.word_similarity(key, KnowledgeEntity.normalized_name),
                    func.coalesce(alias_score, 0.0),
                )
            )

        retrieval_score = func.greatest(*scores)
        statement = (
            select(KnowledgeEntity)
            .where(
                KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                or_(*predicates),
            )
            .order_by(
                retrieval_score.desc(),
                KnowledgeEntity.canonical_name,
                KnowledgeEntity.id,
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def _search_portable_by_similarity(
        self,
        keys: list[str],
        *,
        limit: int,
    ) -> list[KnowledgeEntity]:
        entities = list(
            self.session.scalars(
                select(KnowledgeEntity)
                .where(KnowledgeEntity.entity_type.in_(PLACE_TYPES))
                .order_by(KnowledgeEntity.id)
                .limit(PORTABLE_SIMILARITY_SCAN_LIMIT)
            )
        )
        exact_entities = [
            entity
            for entity in entities
            if any(
                key == name
                for key in keys
                for name in (
                    entity.normalized_name,
                    *(
                        alias.normalized_alias
                        for alias in entity.aliases
                        if alias.status in SEARCHABLE_ALIAS_STATUSES
                    ),
                )
            )
        ]
        if exact_entities:
            return exact_entities[:limit]

        ranked = [
            (_portable_entity_retrieval_score(entity, keys), entity)
            for entity in entities
        ]
        ranked = [
            item
            for item in ranked
            if item[0] >= PORTABLE_RETRIEVAL_MINIMUM_SCORE
        ]
        ranked.sort(
            key=lambda item: (
                -item[0],
                normalize_knowledge_text(item[1].canonical_name),
                item[1].id,
            )
        )
        return [entity for _, entity in ranked[:limit]]

    def search_active_for_autocomplete(
        self,
        query: str,
        region_key: str | None = None,
        *,
        limit: int = 200,
    ) -> list[KnowledgeGraphPlaceRecord]:
        records = self.search_active_by_names([query], limit=max(limit * 3, limit))
        if region_key:
            records = [
                record
                for record in records
                if record.region_key == region_key
                or record.region_key.startswith(f"{region_key},")
                or record.region_key.startswith(f"{region_key}:")
            ]
        return records[:limit]

    def source_signature(self, region_key: str | None = None) -> dict[str, str | int]:
        records = self.list_active_for_planner_research(region_key, limit=100000)
        material = "\n".join(
            f"{record.id}:{record.revision}:{record.source_fetched_at or ''}"
            for record in records
        )
        fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return {
            "storage": self.session.get_bind().dialect.name,
            "regionKey": region_key or "*",
            "fingerprint": fingerprint,
            "rowCount": len(records),
            "revisionSum": sum(record.revision for record in records),
            "maxUpdatedAt": max(
                (record.source_fetched_at.isoformat() for record in records if record.source_fetched_at),
                default="",
            ),
        }

    def iter_statistics_records(
        self, region_key: str | None = None
    ) -> Iterator[PlaceStatisticsRecord]:
        for record in self.list_active_for_planner_research(region_key, limit=100000):
            yield PlaceStatisticsRecord(
                id=record.id,
                region_key=record.region_key,
                place_type=record.place_type,
                status=record.status,
                latitude=float(record.latitude) if record.latitude is not None else None,
                longitude=float(record.longitude) if record.longitude is not None else None,
                opening_hours=record.opening_hours,
                typical_duration_minutes=record.typical_duration_minutes,
                data_confidence=record.data_confidence,
                source_fetched_at=record.source_fetched_at,
                metadata=record.metadata_json,
            )

    def _list_by_region(
        self, region_key: str, *, limit: int
    ) -> list[KnowledgeGraphPlaceRecord]:
        region_predicate = KnowledgeEntity.properties.any(
            and_(
                KnowledgeProperty.key == "region_key",
                or_(
                    KnowledgeProperty.value == region_key,
                    KnowledgeProperty.value.like(f"{region_key},%"),
                    KnowledgeProperty.value.like(f"{region_key}:%"),
                ),
            )
        )
        tourism_predicate = _place_type_matches(
            "museum",
            "tourist attraction",
            "historical",
            "landmark",
            "monument",
            "temple",
            "pagoda",
            "place of worship",
            "church",
            "art gallery",
            "park",
            "garden",
            "scenic",
        )
        dining_predicate = _place_type_matches(
            "restaurant",
            "cafe",
            "coffee",
            "bakery",
            "bistro",
            "food court",
            "fast food",
            "noodle",
            "eatery",
            "diner",
            "dessert",
            "ice cream",
            "tea house",
        )
        base = select(KnowledgeEntity).where(
            KnowledgeEntity.entity_type.in_(PLACE_TYPES),
            region_predicate,
        )
        tourism_limit = max(1, round(limit * 0.55))
        dining_limit = max(0, min(limit - tourism_limit, round(limit * 0.35)))
        support_limit = max(0, limit - tourism_limit - dining_limit)
        entities = [
            *self.session.scalars(
                base.where(tourism_predicate)
                .order_by(KnowledgeEntity.id)
                .limit(tourism_limit)
            ),
            *self.session.scalars(
                base.where(dining_predicate)
                .order_by(KnowledgeEntity.id)
                .limit(dining_limit)
            ),
            *self.session.scalars(
                base.where(~tourism_predicate, ~dining_predicate)
                .order_by(KnowledgeEntity.id)
                .limit(support_limit)
            ),
        ]
        if len(entities) < limit:
            selected_ids = [entity.id for entity in entities]
            fallback = base
            if selected_ids:
                fallback = fallback.where(KnowledgeEntity.id.not_in(selected_ids))
            entities.extend(
                self.session.scalars(
                    fallback.order_by(
                        KnowledgeEntity.entity_type != "TravelPlace",
                        KnowledgeEntity.id,
                    ).limit(limit - len(entities))
                )
            )
        return self._active(self._project(entities))

    @staticmethod
    def _active(records: list[KnowledgeGraphPlaceRecord]) -> list[KnowledgeGraphPlaceRecord]:
        return [record for record in records if place_record_is_search_eligible(record)]

    def _project(
        self, entities: list[KnowledgeEntity]
    ) -> list[KnowledgeGraphPlaceRecord]:
        if not entities:
            return []
        entity_ids = [entity.id for entity in entities]
        properties: dict[str, dict[str, str]] = {entity_id: {} for entity_id in entity_ids}
        for entity_id_batch in _batches(entity_ids, PROJECTION_BATCH_SIZE):
            for prop in self.session.scalars(
                select(KnowledgeProperty).where(
                    KnowledgeProperty.entity_id.in_(entity_id_batch)
                )
            ):
                properties[prop.entity_id][prop.key] = prop.value

        aliases: dict[str, list[str]] = {entity_id: [] for entity_id in entity_ids}
        verified_aliases: dict[str, list[str]] = {
            entity_id: [] for entity_id in entity_ids
        }
        for entity_id_batch in _batches(entity_ids, PROJECTION_BATCH_SIZE):
            for alias in self.session.scalars(
                select(KnowledgeAlias).where(
                    KnowledgeAlias.entity_id.in_(entity_id_batch),
                    KnowledgeAlias.status.in_(SEARCHABLE_ALIAS_STATUSES),
                )
            ):
                aliases[alias.entity_id].append(alias.alias)
                if alias.status in VERIFIED_ALIAS_STATUSES:
                    verified_aliases[alias.entity_id].append(alias.alias)

        images: dict[str, list[KnowledgeGraphImage]] = {
            entity_id: [] for entity_id in entity_ids
        }
        for entity_id_batch in _batches(entity_ids, PROJECTION_BATCH_SIZE):
            for image in self.session.scalars(
                select(KnowledgeEntityImage)
                .where(KnowledgeEntityImage.entity_id.in_(entity_id_batch))
                .order_by(KnowledgeEntityImage.id)
            ):
                if image.entity_id and image.image_url:
                    images[image.entity_id].append(
                        KnowledgeGraphImage(image.image_url)
                    )

        effective_tags: dict[str, list[str]] = {
            entity_id: [] for entity_id in entity_ids
        }
        for entity_id_batch in _batches(entity_ids, PROJECTION_BATCH_SIZE):
            assertions = self.session.scalars(
                select(KnowledgeEntityTagAssertion)
                .where(
                    KnowledgeEntityTagAssertion.entity_id.in_(entity_id_batch),
                    KnowledgeEntityTagAssertion.status.in_(
                        ("verified", "source_backed", "inferred")
                    ),
                    KnowledgeEntityTagAssertion.confidence >= 0.70,
                    or_(
                        KnowledgeEntityTagAssertion.expires_at.is_(None),
                        KnowledgeEntityTagAssertion.expires_at > func.now(),
                    ),
                )
                .order_by(
                    KnowledgeEntityTagAssertion.entity_id,
                    KnowledgeEntityTagAssertion.tag_key,
                    KnowledgeEntityTagAssertion.confidence.desc(),
                )
            )
            for assertion in assertions:
                if assertion.tag_key not in effective_tags[assertion.entity_id]:
                    effective_tags[assertion.entity_id].append(assertion.tag_key)

        return [
            _record_from_entity(
                entity,
                properties[entity.id],
                aliases[entity.id],
                verified_aliases[entity.id],
                images[entity.id],
                effective_tags[entity.id],
            )
            for entity in entities
        ]


def _record_from_entity(
    entity: KnowledgeEntity,
    props: dict[str, str],
    aliases: list[str],
    verified_aliases: list[str],
    images: list[KnowledgeGraphImage],
    effective_tags: list[str],
) -> KnowledgeGraphPlaceRecord:
    metadata = _repair_text_tree(_json_object(props.get("metadata")))
    # ``description`` is stored as a flat property in the legacy graph dump,
    # so it does not pass through ``_repair_text_tree`` above.  Repair it at
    # the same read boundary as the other text fields.
    metadata.setdefault(
        "description",
        repair_cp437_utf8_mojibake(props.get("description") or "") or None,
    )
    stored_tags = metadata.get("tags")
    if not isinstance(stored_tags, list):
        stored_tags = []
    metadata["tags"] = list(
        dict.fromkeys(
            [
                *(str(tag) for tag in stored_tags if isinstance(tag, str)),
                *_tags(props),
                *effective_tags,
            ]
        )
    )
    metadata.setdefault("aliases", aliases)
    metadata.setdefault("verifiedAliases", verified_aliases)
    return KnowledgeGraphPlaceRecord(
        id=entity.id,
        name=repair_cp437_utf8_mojibake(entity.canonical_name),
        place_type=(props.get("place_type") or props.get("place_category") or entity.entity_type),
        address=_text(props.get("address")),
        city=_text(props.get("city")),
        country=_text(props.get("country")),
        country_code=_text(props.get("country_code")),
        primary_area=_text(props.get("primary_area")),
        latitude=_decimal(props.get("latitude")),
        longitude=_decimal(props.get("longitude")),
        data_confidence=props.get("data_confidence") or "medium",
        region_key=props.get("region_key") or "vn,unmapped",
        status=props.get("catalog_status") or "active",
        opening_hours=_json_list_of_objects(props.get("opening_hours")),
        preferred_time_windows=_json_list_of_objects(
            props.get("preferred_time_windows")
        ),
        typical_duration_minutes=_integer(props.get("typical_duration_minutes")),
        source_platform=_text(props.get("source_platform")),
        source_link=_text(props.get("source_url")),
        plus_code=_text(props.get("plus_code")),
        rating=_decimal(props.get("rating")),
        review_count=_integer(props.get("review_count")),
        revision=_integer(props.get("revision")) or 1,
        source_fetched_at=_datetime(props.get("source_fetched_at")),
        metadata_json=metadata,
        images=images,
    )


def _text(value: str | None) -> str | None:
    value = repair_cp437_utf8_mojibake((value or "").strip())
    return value or None


def _place_type_matches(*markers: str):
    return KnowledgeEntity.properties.any(
        and_(
            KnowledgeProperty.key.in_(("place_type", "place_category")),
            or_(
                *(KnowledgeProperty.value.ilike(f"%{marker}%") for marker in markers)
            ),
        )
    )


def _repair_text_tree(value: Any) -> Any:
    """Repair legacy text without changing the shape of metadata JSON."""
    if isinstance(value, str):
        return repair_cp437_utf8_mojibake(value)
    if isinstance(value, list):
        return [_repair_text_tree(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _repair_text_tree(item)
            for key, item in value.items()
        }
    return value


def _decimal(value: str | None) -> Decimal | None:
    try:
        return Decimal(value) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _integer(value: str | None) -> int | None:
    try:
        return int(float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _datetime(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _json_list_of_objects(value: str | None) -> list[dict]:
    try:
        decoded = json.loads(value) if value else []
    except (TypeError, ValueError):
        return []
    return [item for item in decoded if isinstance(item, dict)] if isinstance(decoded, list) else []


def _tags(props: dict[str, str]) -> list[str]:
    values = [
        props.get("place_category"),
        props.get("source_category"),
        props.get("accommodation_type"),
    ]
    return [value for value in values if value]


def _portable_entity_retrieval_score(
    entity: KnowledgeEntity,
    keys: list[str],
) -> float:
    names = [entity.normalized_name]
    names.extend(
        alias.normalized_alias
        for alias in entity.aliases
        if alias.status in SEARCHABLE_ALIAS_STATUSES
    )
    return max(
        (
            _portable_text_similarity(key, name)
            for key in keys
            for name in names
        ),
        default=0.0,
    )


def _portable_text_similarity(query: str, value: str) -> float:
    """Approximate the PostgreSQL shortlist for isolated SQLite tests."""
    query_key = normalize_knowledge_text(query)
    value_key = normalize_knowledge_text(value)
    if not query_key or not value_key:
        return 0.0
    if query_key == value_key:
        return 2.0

    query_tokens = query_key.split()
    value_tokens = value_key.split()
    if _contains_token_sequence(value_tokens, query_tokens):
        return max(0.80, 0.92 - 0.02 * (len(value_tokens) - len(query_tokens)))
    if _contains_token_sequence(query_tokens, value_tokens):
        return max(0.75, 0.88 - 0.02 * (len(query_tokens) - len(value_tokens)))
    return SequenceMatcher(None, query_key, value_key).ratio()


def _contains_token_sequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[index:index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def _batches(values: list[str], size: int) -> Iterator[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]
