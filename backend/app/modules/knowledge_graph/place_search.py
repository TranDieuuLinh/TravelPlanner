"""Read canonical venue suggestions from the Knowledge Graph."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research.repository import ScopeResolutionRepository
from app.modules.knowledge_graph.research.schema import PLACE_TYPES
from app.modules.knowledge_graph.text import normalize_knowledge_text


@dataclass(frozen=True)
class KnowledgeGraphPlaceMatch:
    entity_id: str
    name: str
    entity_type: str
    status: str
    address: str | None
    latitude: float
    longitude: float
    rating: float | None = None
    review_count: int | None = None
    price_level: int | None = None
    image_url: str | None = None
    phone: str | None = None
    website: str | None = None
    opening_hours: list[str] | None = None


class KnowledgeGraphPlaceSearchRepository:
    """Search promoted graph entities, never unreviewed import staging rows."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        query: str,
        destination: str | None,
        *,
        limit: int = 5,
    ) -> list[KnowledgeGraphPlaceMatch]:
        query_key = normalize_knowledge_text(query)
        if not query_key or limit < 1:
            return []

        area_ids = self._destination_area_ids(destination)
        if destination and not area_ids:
            return []

        pattern = f"%{query_key}%"
        statement = (
            select(KnowledgeEntity)
            .join(
                KnowledgeRelationship,
                KnowledgeRelationship.from_entity_id == KnowledgeEntity.id,
            )
            .where(
                KnowledgeEntity.entity_type.in_(PLACE_TYPES),
                KnowledgeRelationship.relationship_type == "LOCATED_IN",
                or_(
                    KnowledgeEntity.normalized_name.ilike(pattern),
                    KnowledgeEntity.aliases.any(
                        KnowledgeAlias.normalized_alias.ilike(pattern)
                    ),
                ),
            )
        )
        if area_ids:
            statement = statement.where(
                KnowledgeRelationship.to_entity_id.in_(area_ids)
            )

        # Fetch a bounded candidate set, then apply the same deterministic
        # accent-insensitive ranking on SQLite and PostgreSQL.
        entities = list(
            self.db.scalars(
                statement.distinct().order_by(KnowledgeEntity.id).limit(200)
            )
        )
        if not entities:
            return []

        entity_ids = [entity.id for entity in entities]
        aliases_by_entity: dict[str, list[str]] = {entity_id: [] for entity_id in entity_ids}
        for alias in self.db.scalars(
            select(KnowledgeAlias).where(KnowledgeAlias.entity_id.in_(entity_ids))
        ):
            aliases_by_entity[alias.entity_id].append(alias.normalized_alias)

        properties_by_entity: dict[str, dict[str, KnowledgeProperty]] = {
            entity_id: {} for entity_id in entity_ids
        }
        for prop in self.db.scalars(
            select(KnowledgeProperty).where(KnowledgeProperty.entity_id.in_(entity_ids))
        ):
            properties_by_entity[prop.entity_id][prop.key] = prop

        ranked: list[tuple[int, int, float, str, KnowledgeGraphPlaceMatch]] = []
        for entity in entities:
            score = _name_match_score(
                query_key,
                [entity.normalized_name, *aliases_by_entity[entity.id]],
            )
            if score is None:
                continue
            match = _to_place_match(entity, properties_by_entity[entity.id])
            if match is None:
                continue
            ranked.append(
                (
                    score,
                    -(match.review_count or 0),
                    -(match.rating or 0.0),
                    normalize_knowledge_text(match.name),
                    match,
                )
            )

        ranked.sort(key=lambda item: item[:-1])
        return [item[-1] for item in ranked[:limit]]

    def _destination_area_ids(self, destination: str | None) -> set[str]:
        if not destination or not destination.strip():
            return set()
        scope = ScopeResolutionRepository(self.db)
        root = scope.resolve_area_by_name(destination)
        if root is None:
            return set()
        descendants = scope.traverse_part_of_descendants(
            root.id,
            max_depth=4,
            limit=1000,
        )
        return {root.id, *(area.id for area in descendants)}


def _name_match_score(query_key: str, names: list[str]) -> int | None:
    scores: list[int] = []
    for value in names:
        name_key = normalize_knowledge_text(value)
        if name_key == query_key:
            scores.append(0)
        elif name_key.startswith(query_key):
            scores.append(1)
        elif any(word.startswith(query_key) for word in name_key.split()):
            scores.append(2)
        # An arbitrary middle-of-word substring is a low-confidence identity
        # match. Exclude it so the service can ask the external fallback.
    return min(scores) if scores else None


def _to_place_match(
    entity: KnowledgeEntity,
    properties: dict[str, KnowledgeProperty],
) -> KnowledgeGraphPlaceMatch | None:
    latitude = _finite_float(_property_value(properties, "latitude"))
    longitude = _finite_float(_property_value(properties, "longitude"))
    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return None

    return KnowledgeGraphPlaceMatch(
        entity_id=entity.id,
        name=entity.canonical_name,
        entity_type=entity.entity_type,
        status=entity.status,
        address=_property_value(properties, "address"),
        latitude=latitude,
        longitude=longitude,
        rating=_finite_float(_property_value(properties, "rating")),
        review_count=_integer(_property_value(properties, "review_count")),
        price_level=_integer(_property_value(properties, "price_level")),
        image_url=(
            _property_value(properties, "image_url")
            or _property_value(properties, "image")
        ),
        phone=_property_value(properties, "phone"),
        website=_property_value(properties, "website"),
        opening_hours=_string_list(_property_value(properties, "opening_hours")),
    )


def _property_value(
    properties: dict[str, KnowledgeProperty],
    key: str,
) -> str | None:
    prop = properties.get(key)
    if prop is None:
        return None
    value = prop.value.strip()
    return value or None


def _finite_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _integer(value: str | None) -> int | None:
    number = _finite_float(value)
    return int(number) if number is not None else None


def _string_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    try:
        decoded: Any = json.loads(value)
    except (TypeError, ValueError):
        decoded = None
    if isinstance(decoded, list):
        result = [str(item).strip() for item in decoded if str(item).strip()]
        return result or None
    return [value]
