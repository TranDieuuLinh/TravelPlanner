from __future__ import annotations

from collections import defaultdict
import json
from math import isfinite
import re

from app.modules.place_checker.subplaces.contract import (
    SubplaceOfferItemContext,
    SubplaceGroup,
    SubplaceSummary,
)


SUBPLACES_BY_PARENT_SQL = """
WITH ranked AS (
    SELECT relationship.from_entity_id AS parent_place_id,
           parent.canonical_name AS parent_place_name,
           child.id AS place_id,
           child.canonical_name AS name,
           count(*) OVER (
               PARTITION BY relationship.from_entity_id
           ) AS total_count,
           row_number() OVER (
               PARTITION BY relationship.from_entity_id
               ORDER BY relationship.created_at, child.canonical_name, child.id
           ) AS child_order
    FROM knowledge_relationships relationship
    JOIN knowledge_entities parent
      ON parent.id = relationship.from_entity_id
     AND parent.entity_type = 'TravelPlace'
     AND parent.status <> 'rejected'
    JOIN knowledge_entities child
      ON child.id = relationship.to_entity_id
     AND child.entity_type = 'SubPlace'
     AND child.status <> 'rejected'
    WHERE relationship.relationship_type = 'Has_Subplace'
      AND relationship.from_entity_id = ANY($1::text[])
)
SELECT ranked.parent_place_id, ranked.parent_place_name,
       ranked.place_id, ranked.name,
       ranked.total_count, ranked.child_order,
       properties.address, properties.latitude, properties.longitude,
       properties.image, properties.time_duration, properties.price_min,
       properties.rating, properties.review_count,
       COALESCE(activities.offer_items, '[]'::jsonb)::text AS offer_items
FROM ranked
LEFT JOIN LATERAL (
    SELECT max(property.value) FILTER (
               WHERE property.key = 'address'
           ) AS address,
           max(property.value) FILTER (
               WHERE property.key = 'latitude'
           ) AS latitude,
           max(property.value) FILTER (
               WHERE property.key = 'longitude'
           ) AS longitude,
           max(property.value) FILTER (
               WHERE property.key IN (
                   'image', 'image_url', 'imageUrl', 'image_urls', 'imageUrls', 'images'
               )
           ) AS image,
           max(property.value) FILTER (
               WHERE property.key = 'time_duration'
           ) AS time_duration,
           max(property.value) FILTER (
               WHERE property.key = 'price_min'
           ) AS price_min,
           max(property.value) FILTER (
               WHERE property.key = 'rating'
           ) AS rating,
           max(property.value) FILTER (
               WHERE property.key = 'review_count'
           ) AS review_count
    FROM knowledge_properties property
    WHERE property.entity_id = ranked.place_id
) properties ON true
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
               jsonb_build_object(
                   'relationshipType', 'Offer_Item',
                   'activityItemId', item.id,
                   'activityItemName', item.canonical_name,
                   'action', CASE
                       WHEN jsonb_typeof(offer.recommendations::jsonb) = 'object'
                       THEN offer.recommendations::jsonb ->> 'action'
                       ELSE NULL
                   END,
                   'displayTemplate', CASE
                       WHEN jsonb_typeof(offer.recommendations::jsonb) = 'object'
                       THEN offer.recommendations::jsonb ->> 'displayTemplate'
                       ELSE NULL
                   END
               )
               ORDER BY offer.created_at, item.canonical_name, item.id
           ) AS offer_items
    FROM knowledge_relationships offer
    JOIN knowledge_entities item
      ON item.id = offer.to_entity_id
     AND item.entity_type = 'ActivityItem'
     AND item.status <> 'rejected'
    WHERE offer.from_entity_id = ranked.place_id
      AND offer.relationship_type = 'Offer_Item'
) activities ON true
WHERE ranked.child_order <= $2
ORDER BY ranked.parent_place_id, ranked.child_order
"""


def _coordinate(
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> float | None:
    try:
        coordinate = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not isfinite(coordinate) or not minimum <= coordinate <= maximum:
        return None
    return coordinate


def _number(
    value: object,
    *,
    minimum: float = 0,
    maximum: float | None = None,
) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or number < minimum or (
        maximum is not None and number > maximum
    ):
        return None
    return number


def _duration_minutes(value: object) -> int | None:
    if value in (None, ""):
        return None
    text = str(value).strip().upper()
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", text)
    if match:
        minutes = int(match.group(1) or 0) * 60 + int(match.group(2) or 0)
    else:
        try:
            minutes = int(float(text))
        except ValueError:
            return None
    return minutes if 1 <= minutes <= 1440 else None


def _offer_items(value: object) -> list[SubplaceOfferItemContext]:
    if not value:
        return []
    try:
        payload = json.loads(value) if isinstance(value, str) else value
        if not isinstance(payload, list):
            return []
        return [
            SubplaceOfferItemContext.model_validate(item)
            for item in payload[:20]
            if isinstance(item, dict)
        ]
    except (TypeError, ValueError):
        return []


class PostgresSubplaceMixin:
    async def list_subplaces(
        self,
        parent_place_ids: list[str],
        *,
        per_parent_limit: int = 50,
    ) -> list[SubplaceGroup]:
        parent_ids = list(dict.fromkeys(parent_place_ids))
        if not parent_ids:
            return []
        rows = await self._fetch(
            SUBPLACES_BY_PARENT_SQL,
            parent_ids,
            max(1, min(per_parent_limit, 50)),
        )
        items_by_parent: dict[str, list[SubplaceSummary]] = defaultdict(list)
        total_by_parent: dict[str, int] = {}
        name_by_parent: dict[str, str] = {}
        for row in rows:
            parent_id = str(row["parent_place_id"])
            image_urls = self._image_urls({"image": row["image"]})
            items_by_parent[parent_id].append(
                SubplaceSummary(
                    place_id=str(row["place_id"]),
                    name=str(row["name"]),
                    address=(str(row["address"]).strip() if row["address"] else None),
                    latitude=_coordinate(
                        row["latitude"],
                        minimum=-90,
                        maximum=90,
                    ),
                    longitude=_coordinate(
                        row["longitude"],
                        minimum=-180,
                        maximum=180,
                    ),
                    image_url=image_urls[0] if image_urls else None,
                    duration_minutes=_duration_minutes(row["time_duration"]),
                    cost_per_person=_number(row["price_min"]),
                    rating=_number(row["rating"], maximum=5),
                    review_count=(
                        int(review_count)
                        if (review_count := _number(row["review_count"])) is not None
                        else None
                    ),
                    offer_items=_offer_items(row["offer_items"]),
                )
            )
            total_by_parent[parent_id] = int(row["total_count"])
            name_by_parent[parent_id] = str(row["parent_place_name"])
        return [
            SubplaceGroup(
                parent_place_id=parent_id,
                total_count=total_by_parent[parent_id],
                items=items_by_parent[parent_id],
                parent_place_name=name_by_parent[parent_id],
            )
            for parent_id in parent_ids
            if parent_id in total_by_parent
        ]
