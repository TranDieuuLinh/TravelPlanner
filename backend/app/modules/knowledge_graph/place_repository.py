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
from typing import Any, Iterator

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
)
from app.modules.knowledge_graph.research.schema import PLACE_TYPES
from app.modules.knowledge_graph.text import normalize_knowledge_text
from app.modules.places.auto_statistics.domain import PlaceStatisticsRecord
from app.modules.places.model import KnowledgeEntityImage


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
        entity = self.session.scalar(
            select(KnowledgeEntity).where(
                KnowledgeEntity.id == entity_id,
                KnowledgeEntity.entity_type.in_(PLACE_TYPES),
            )
        )
        records = self._project([entity] if entity is not None else [])
        return records[0] if records else None

    def list_for_place_selection(
        self, region_key: str, *, limit: int = 10000
    ) -> list[KnowledgeGraphPlaceRecord]:
        return self._list_by_region(region_key, limit=limit)

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
        keys = [normalize_knowledge_text(name) for name in names]
        keys = [key for key in keys if key]
        if not keys:
            return []
        predicates = []
        for key in keys:
            pattern = f"%{key}%"
            predicates.extend(
                [
                    KnowledgeEntity.normalized_name.ilike(pattern),
                    KnowledgeEntity.aliases.any(
                        KnowledgeAlias.normalized_alias.ilike(pattern)
                    ),
                ]
            )
        entities = list(
            self.session.scalars(
                select(KnowledgeEntity)
                .where(
                    KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                    or_(*predicates),
                )
                .order_by(KnowledgeEntity.id)
                .limit(limit)
            )
        )
        return self._active(self._project(entities))

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
        region_property = KnowledgeProperty
        entities = list(
            self.session.scalars(
                select(KnowledgeEntity)
                .join(
                    region_property,
                    region_property.entity_id == KnowledgeEntity.id,
                )
                .where(
                    KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                    region_property.key == "region_key",
                    or_(
                        region_property.value == region_key,
                        region_property.value.like(f"{region_key},%"),
                        region_property.value.like(f"{region_key}:%"),
                    ),
                )
                .distinct()
                .order_by(KnowledgeEntity.id)
                .limit(limit)
            )
        )
        return self._active(self._project(entities))

    @staticmethod
    def _active(records: list[KnowledgeGraphPlaceRecord]) -> list[KnowledgeGraphPlaceRecord]:
        return [record for record in records if record.status == "active"]

    def _project(
        self, entities: list[KnowledgeEntity]
    ) -> list[KnowledgeGraphPlaceRecord]:
        if not entities:
            return []
        entity_ids = [entity.id for entity in entities]
        properties: dict[str, dict[str, str]] = {entity_id: {} for entity_id in entity_ids}
        for prop in self.session.scalars(
            select(KnowledgeProperty).where(KnowledgeProperty.entity_id.in_(entity_ids))
        ):
            properties[prop.entity_id][prop.key] = prop.value

        aliases: dict[str, list[str]] = {entity_id: [] for entity_id in entity_ids}
        for alias in self.session.scalars(
            select(KnowledgeAlias).where(KnowledgeAlias.entity_id.in_(entity_ids))
        ):
            aliases[alias.entity_id].append(alias.alias)

        images: dict[str, list[KnowledgeGraphImage]] = {
            entity_id: [] for entity_id in entity_ids
        }
        for image in self.session.scalars(
            select(KnowledgeEntityImage)
            .where(KnowledgeEntityImage.entity_id.in_(entity_ids))
            .order_by(KnowledgeEntityImage.id)
        ):
            if image.entity_id and image.image_url:
                images[image.entity_id].append(KnowledgeGraphImage(image.image_url))

        return [
            _record_from_entity(
                entity,
                properties[entity.id],
                aliases[entity.id],
                images[entity.id],
            )
            for entity in entities
        ]


def _record_from_entity(
    entity: KnowledgeEntity,
    props: dict[str, str],
    aliases: list[str],
    images: list[KnowledgeGraphImage],
) -> KnowledgeGraphPlaceRecord:
    metadata = _json_object(props.get("metadata"))
    metadata.setdefault("description", props.get("description"))
    metadata.setdefault("tags", _tags(props))
    metadata.setdefault("aliases", aliases)
    return KnowledgeGraphPlaceRecord(
        id=entity.id,
        name=entity.canonical_name,
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
    value = (value or "").strip()
    return value or None


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
