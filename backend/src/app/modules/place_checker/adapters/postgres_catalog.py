from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.modules.place_checker.contract import AdmResolution, AdmResolutionStatus
from app.modules.place_checker.enums import CostTier, OperationalStatus
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import AdministrativeArea, PlaceProviderCandidate
from app.shared.tools.search_places.normalization import normalize_text


PLACE_TYPES = {"TravelPlace", "Restaurant", "DrinkDessert", "Accommodation"}
TYPE_BY_HINT = {
    "travel place": {"TravelPlace"},
    "attraction": {"TravelPlace"},
    "experience": {"TravelPlace"},
    "restaurant": {"Restaurant"},
    "food": {"Restaurant"},
    "food venue": {"Restaurant"},
    "cafe": {"DrinkDessert"},
    "coffee": {"DrinkDessert"},
    "drink": {"DrinkDessert"},
    "drink dessert": {"DrinkDessert"},
    "hotel": {"Accommodation"},
    "accommodation": {"Accommodation"},
}
CANONICAL_TYPE = {
    "TravelPlace": "travel_place",
    "Restaurant": "restaurant",
    "DrinkDessert": "drink_dessert",
    "Accommodation": "accommodation",
}
TOURISM_EXPERIENCE_MARKERS = {
    "cam trai",
    "cuoi ngua",
    "di bo",
    "di dao",
    "ghe chua",
    "mua do luu niem",
    "ngam ",
    "qua cau",
    "tham ",
    "tham gia hoi cho",
    "tham quan",
    "trai nghiem van hoa",
    "vui choi danh cho tre em",
    "xem bieu dien nghe thuat",
}


def _asyncpg_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgresql+asyncpg://", "postgresql://"
    )


class PostgresPlaceCatalog:
    """Read-only PlaceChecker adapter over the normalized Knowledge Graph."""

    provider_name = "knowledge_graph"

    def __init__(self, database_url: str, *, command_timeout: float = 15.0) -> None:
        self.database_url = _asyncpg_url(database_url)
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=self.command_timeout,
            )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def resolve(self, input_name: str) -> AdmResolution:
        normalized = normalize_text(input_name)
        pool = await self._get_pool()
        rows = await pool.fetch(
            """
            SELECT e.id, e.canonical_name, e.entity_type,
                   GREATEST(
                       similarity(e.normalized_name, $1),
                       similarity(replace(e.normalized_name, ' ', ''), replace($1, ' ', '')),
                       COALESCE(max(similarity(a.normalized_alias, $1)), 0)
                   ) AS score
            FROM knowledge_entities e
            LEFT JOIN knowledge_aliases a ON a.entity_id = e.id
            WHERE e.entity_type IN ('ADM0', 'ADM1', 'ADM2')
              AND (
                  e.normalized_name % $1
                  OR replace(e.normalized_name, ' ', '') = replace($1, ' ', '')
                  OR a.normalized_alias % $1
              )
            GROUP BY e.id
            ORDER BY score DESC, e.canonical_name
            LIMIT 5
            """,
            normalized,
        )
        if not rows or float(rows[0]["score"]) < 0.45:
            return AdmResolution(
                input_name=input_name,
                status=AdmResolutionStatus.unresolved,
            )
        top = rows[0]
        alternatives = [row["canonical_name"] for row in rows[1:]]
        if len(rows) > 1 and float(top["score"]) - float(rows[1]["score"]) < 0.08:
            return AdmResolution(
                input_name=input_name,
                status=AdmResolutionStatus.ambiguous,
                alternatives=[top["canonical_name"], *alternatives],
            )
        level = top["entity_type"].casefold()
        return AdmResolution(
            input_name=input_name,
            status=AdmResolutionStatus.resolved,
            adm_id=top["id"],
            canonical_name=top["canonical_name"],
            country_code="VN",
            region_key=f"vn,{level},{normalize_text(top['canonical_name']).replace(' ', '_')}",
            alternatives=alternatives,
        )

    async def search(
        self,
        lookup_names: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
        anchor_place_id: str | None = None,
    ) -> list[PlaceProviderCandidate]:
        normalized = [normalize_text(name) for name in lookup_names if normalize_text(name)]
        query = normalized[0] if normalized else ""
        requested_types = self._types_for_hint(place_type_hint)
        # SearchPlacesTool performs the final score. Returning a wider KG window
        # lets proximity and diversity policies choose among nearby candidates.
        fetch_limit = min(50, max(limit * 10, 20))
        pool = await self._get_pool()
        rows = await pool.fetch(
            """
            WITH scoped AS (
                SELECT DISTINCT e.id
                FROM knowledge_entities e
                JOIN knowledge_relationships location
                  ON location.from_entity_id = e.id
                 AND location.relationship_type = 'Located_In'
                LEFT JOIN knowledge_relationships parent
                  ON parent.from_entity_id = location.to_entity_id
                 AND parent.relationship_type = 'Located_In'
                WHERE e.entity_type = ANY($3::text[])
                  AND (location.to_entity_id = $2 OR parent.to_entity_id = $2)
            )
            SELECT e.id, e.canonical_name, e.entity_type, e.status,
                   aliases.values AS aliases,
                   props.address, props.latitude, props.longitude,
                   props.rating, props.review_count, props.updated_at,
                   tags.values AS tags,
                   CASE
                       WHEN $5::text IS NULL THEN 0
                       WHEN EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Must_Visit'
                       ) THEN 0.95
                       WHEN EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Near'
                       ) THEN 0.85
                       WHEN EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Special_Experience'
                       ) THEN 0.75
                       WHEN EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Offer_Item'
                       ) THEN 0.72
                       WHEN EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Has_Style'
                       ) THEN 0.55
                       WHEN EXISTS (
                           SELECT 1
                           FROM knowledge_relationships anchor_location
                           JOIN knowledge_relationships area_edge
                             ON area_edge.from_entity_id = anchor_location.to_entity_id
                            AND area_edge.to_entity_id = e.id
                           WHERE anchor_location.from_entity_id = $5::text
                             AND anchor_location.relationship_type = 'Located_In'
                             AND area_edge.relationship_type = 'Must_Visit'
                       ) THEN 0.78
                       WHEN EXISTS (
                           SELECT 1
                           FROM knowledge_relationships anchor_location
                           JOIN knowledge_relationships area_edge
                             ON area_edge.from_entity_id = anchor_location.to_entity_id
                            AND area_edge.to_entity_id = e.id
                           WHERE anchor_location.from_entity_id = $5::text
                             AND anchor_location.relationship_type = 'Located_In'
                             AND area_edge.relationship_type = 'Special_Experience'
                       ) THEN 0.70
                       ELSE 0
                   END AS relationship_score,
                   CASE
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Must_Visit'
                       ) THEN 'relation:must_visit'
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Near'
                       ) THEN 'relation:near'
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Special_Experience'
                       ) THEN 'relation:special_experience'
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Offer_Item'
                       ) THEN 'relation:offer_item'
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1 FROM knowledge_relationships edge
                           WHERE (
                               (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
                               OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
                           ) AND edge.relationship_type = 'Has_Style'
                       ) THEN 'relation:has_style'
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1
                           FROM knowledge_relationships anchor_location
                           JOIN knowledge_relationships area_edge
                             ON area_edge.from_entity_id = anchor_location.to_entity_id
                            AND area_edge.to_entity_id = e.id
                           WHERE anchor_location.from_entity_id = $5::text
                             AND anchor_location.relationship_type = 'Located_In'
                             AND area_edge.relationship_type = 'Must_Visit'
                       ) THEN 'relation:area_must_visit'
                       WHEN $5::text IS NOT NULL AND EXISTS (
                           SELECT 1
                           FROM knowledge_relationships anchor_location
                           JOIN knowledge_relationships area_edge
                             ON area_edge.from_entity_id = anchor_location.to_entity_id
                            AND area_edge.to_entity_id = e.id
                           WHERE anchor_location.from_entity_id = $5::text
                             AND anchor_location.relationship_type = 'Located_In'
                             AND area_edge.relationship_type = 'Special_Experience'
                       ) THEN 'relation:area_special_experience'
                       ELSE NULL
                   END AS anchor_relation,
                   GREATEST(
                       similarity(e.normalized_name, $1),
                       COALESCE(aliases.score, 0),
                       COALESCE(tags.score, 0)
                   ) AS match_score
            FROM scoped s
            JOIN knowledge_entities e ON e.id = s.id
            LEFT JOIN LATERAL (
                SELECT array_agg(DISTINCT a.alias) AS values,
                       max(similarity(a.normalized_alias, $1)) AS score
                FROM knowledge_aliases a WHERE a.entity_id = e.id
            ) aliases ON true
            LEFT JOIN LATERAL (
                SELECT
                    max(p.value) FILTER (WHERE p.key = 'address') AS address,
                    max(p.value) FILTER (WHERE p.key = 'latitude') AS latitude,
                    max(p.value) FILTER (WHERE p.key = 'longitude') AS longitude,
                    max(p.value) FILTER (WHERE p.key = 'rating') AS rating,
                    max(p.value) FILTER (WHERE p.key = 'review_count') AS review_count,
                    max(p.updated_at) AS updated_at
                FROM knowledge_properties p WHERE p.entity_id = e.id
            ) props ON true
            LEFT JOIN LATERAL (
                SELECT array_agg(DISTINCT
                           CASE r.relationship_type
                               WHEN 'Special_Experience' THEN 'experience:' || target.canonical_name
                               WHEN 'Offer_Item' THEN 'item:' || target.canonical_name
                               WHEN 'Has_Style' THEN 'style:' || target.canonical_name
                               ELSE 'relation:' || lower(r.relationship_type)
                           END
                       ) AS values,
                       max(similarity(target.normalized_name, $1)) AS score
                FROM (
                    SELECT r.relationship_type, r.to_entity_id
                    FROM knowledge_relationships r
                    WHERE r.from_entity_id = e.id
                      AND r.relationship_type IN (
                          'Special_Experience', 'Offer_Item', 'Has_Style'
                      )
                    UNION ALL
                    SELECT r.relationship_type, r.to_entity_id
                    FROM knowledge_relationships location
                    JOIN knowledge_relationships r
                      ON r.from_entity_id = location.to_entity_id
                     AND r.relationship_type IN (
                         'Special_Experience', 'SPECIAL_EXPERIENCE'
                     )
                    WHERE location.from_entity_id = e.id
                      AND location.relationship_type IN ('Located_In', 'LOCATED_IN')
                ) r
                JOIN knowledge_entities target ON target.id = r.to_entity_id
            ) tags ON true
            WHERE $1 = ''
               OR (
                   $5::text IS NOT NULL
                   AND EXISTS (
                       SELECT 1 FROM knowledge_relationships relation_edge
                       WHERE (
                           (relation_edge.from_entity_id = $5::text AND relation_edge.to_entity_id = e.id)
                           OR (relation_edge.from_entity_id = e.id AND relation_edge.to_entity_id = $5::text)
                       )
                       AND relation_edge.relationship_type IN (
                           'Near', 'Must_Visit', 'Special_Experience', 'Offer_Item', 'Has_Style'
                       )
                   )
                   OR EXISTS (
                       SELECT 1
                       FROM knowledge_relationships anchor_location
                       JOIN knowledge_relationships area_edge
                         ON area_edge.from_entity_id = anchor_location.to_entity_id
                        AND area_edge.to_entity_id = e.id
                       WHERE anchor_location.from_entity_id = $5::text
                         AND anchor_location.relationship_type = 'Located_In'
                         AND area_edge.relationship_type IN ('Must_Visit', 'Special_Experience')
                   )
               )
               OR similarity(e.normalized_name, $1) > 0.16
               OR COALESCE(aliases.score, 0) > 0.16
               OR COALESCE(tags.score, 0) > 0.16
               OR cardinality($3::text[]) < 4
            ORDER BY relationship_score DESC,
                     match_score DESC,
                     NULLIF(props.rating, '')::double precision DESC NULLS LAST,
                     NULLIF(props.review_count, '')::bigint DESC NULLS LAST,
                     e.canonical_name
            LIMIT $4
            """,
            query,
            input_adm.adm_id,
            sorted(requested_types),
            fetch_limit,
            anchor_place_id,
        )
        candidates = [self._candidate(row, input_adm) for row in rows]
        if self._is_generic_travel_discovery(query):
            candidates = [
                candidate
                for candidate in candidates
                if candidate.canonical_type != "travel_place"
                or self._has_tourism_experience(candidate.tags)
            ]
            candidates = self._cap_tourism_experience_groups(
                candidates,
                per_group=max(2, min(12, limit // 3)),
            )
        return candidates

    async def get_many(self, place_ids: list[str]) -> dict[str, PlaceMetadata]:
        if not place_ids:
            return {}
        pool = await self._get_pool()
        entity_rows = await pool.fetch(
            "SELECT id, entity_type FROM knowledge_entities WHERE id = ANY($1::text[])",
            place_ids,
        )
        property_rows = await pool.fetch(
            """
            SELECT entity_id, key, value, source, updated_at
            FROM knowledge_properties
            WHERE entity_id = ANY($1::text[])
            """,
            place_ids,
        )
        tag_rows = await pool.fetch(
            """
            SELECT r.from_entity_id AS entity_id, r.relationship_type,
                   target.canonical_name
            FROM knowledge_relationships r
            JOIN knowledge_entities target ON target.id = r.to_entity_id
            WHERE r.from_entity_id = ANY($1::text[])
              AND r.relationship_type IN ('Special_Experience', 'Offer_Item')
            """,
            place_ids,
        )
        properties: dict[str, dict[str, Any]] = defaultdict(dict)
        fetched_at: dict[str, datetime] = {}
        for row in property_rows:
            properties[row["entity_id"]][row["key"]] = row["value"]
            current = fetched_at.get(row["entity_id"])
            if current is None or row["updated_at"] > current:
                fetched_at[row["entity_id"]] = row["updated_at"]
        tags: dict[str, list[str]] = defaultdict(list)
        for row in tag_rows:
            prefix = "experience" if row["relationship_type"] == "Special_Experience" else "item"
            tags[row["entity_id"]].append(f"{prefix}:{row['canonical_name']}")
        return {
            row["id"]: self._metadata(
                row["id"],
                row["entity_type"],
                properties[row["id"]],
                tags[row["id"]],
                fetched_at.get(row["id"]),
            )
            for row in entity_rows
        }

    @staticmethod
    def _types_for_hint(place_type_hint: str | None) -> set[str]:
        if not place_type_hint:
            return PLACE_TYPES
        return TYPE_BY_HINT.get(normalize_text(place_type_hint), PLACE_TYPES)

    @staticmethod
    def _is_generic_travel_discovery(query: str) -> bool:
        return "travel place" in normalize_text(query)

    @staticmethod
    def _has_tourism_experience(tags: list[str]) -> bool:
        experiences = [
            normalize_text(tag.split(":", 1)[1])
            for tag in tags
            if tag.startswith("experience:")
        ]
        return any(
            marker in experience
            for experience in experiences
            for marker in TOURISM_EXPERIENCE_MARKERS
        )

    @classmethod
    def _cap_tourism_experience_groups(
        cls,
        candidates: list[PlaceProviderCandidate],
        *,
        per_group: int = 2,
    ) -> list[PlaceProviderCandidate]:
        counts: dict[str, int] = defaultdict(int)
        selected: list[PlaceProviderCandidate] = []
        for candidate in candidates:
            bucket = cls._tourism_experience_bucket(candidate.tags)
            if bucket is None or counts[bucket] >= per_group:
                continue
            counts[bucket] += 1
            selected.append(candidate)
        return selected

    @staticmethod
    def _tourism_experience_bucket(tags: list[str]) -> str | None:
        values = [
            normalize_text(tag.split(":", 1)[1])
            for tag in tags
            if tag.startswith("experience:")
        ]
        groups = (
            ("camping", ("cam trai",)),
            ("culture", ("van hoa", "tin nguong", "ghe chua")),
            ("landmark", ("dia danh", "ngam ", "qua cau")),
            ("outdoor_walk", ("di dao", "di bo")),
            ("family", ("vui choi danh cho tre em",)),
            ("performance", ("xem bieu dien",)),
            ("event", ("hoi cho",)),
            ("souvenir", ("do luu niem",)),
            ("horse_riding", ("cuoi ngua",)),
        )
        for group, markers in groups:
            if any(marker in value for marker in markers for value in values):
                return group
        if any(
            marker in value
            for value in values
            for marker in TOURISM_EXPERIENCE_MARKERS
        ):
            return "other_tourism"
        return None

    @staticmethod
    def _candidate(row, input_adm: AdministrativeArea) -> PlaceProviderCandidate:
        category = CANONICAL_TYPE.get(row["entity_type"], normalize_text(row["entity_type"]))
        rating = PostgresPlaceCatalog._number(row["rating"])
        confidence = 0.75 if rating is None else min(0.98, 0.65 + rating / 20)
        raw_tags = list(row["tags"] or [])
        if row["anchor_relation"]:
            raw_tags.append(row["anchor_relation"])
        tags = [category.replace("_", " "), *raw_tags]
        return PlaceProviderCandidate(
            provider="knowledge_graph",
            entity_id=row["id"],
            name=row["canonical_name"],
            aliases=list(row["aliases"] or []),
            address=row["address"],
            coordinates=PostgresPlaceCatalog._coordinates(
                row["latitude"], row["longitude"]
            ),
            adm_ids=[input_adm.adm_id],
            adm_names=[input_adm.name],
            canonical_type=category,
            tags=list(dict.fromkeys(tags)),
            rating=rating,
            review_count=PostgresPlaceCatalog._integer(row["review_count"]),
            relationship_score=float(row["relationship_score"] or 0),
            data_confidence=confidence,
            fetched_at=row["updated_at"],
        )

    @classmethod
    def _metadata(
        cls,
        place_id: str,
        entity_type: str,
        values: dict[str, Any],
        tags: list[str],
        fetched_at: datetime | None,
    ) -> PlaceMetadata:
        minimum_cost = cls._number(values.get("price_min"))
        maximum_cost = cls._number(values.get("price_max"))
        duration = cls._duration(values.get("time_duration"))
        opening = cls._opening_hours(values)
        category = CANONICAL_TYPE.get(entity_type, normalize_text(entity_type))
        child_tag = any("vui chơi dành cho trẻ em" in tag.casefold() for tag in tags)
        return PlaceMetadata(
            place_id=place_id,
            coordinates=cls._coordinates(values.get("latitude"), values.get("longitude")),
            address=values.get("address"),
            category=category,
            tags=list(dict.fromkeys([category.replace("_", " "), *tags])),
            rating=cls._number(values.get("rating")),
            review_count=cls._integer(values.get("review_count")),
            minimum_duration_minutes=(max(15, duration - 30) if duration else None),
            typical_duration_minutes=duration,
            maximum_duration_minutes=(min(1440, duration + 30) if duration else None),
            cost_tier=cls._cost_tier(maximum_cost),
            cost_currency="VND" if minimum_cost is not None or maximum_cost is not None else None,
            minimum_cost=minimum_cost,
            typical_cost=cls._typical_cost(minimum_cost, maximum_cost),
            maximum_cost=maximum_cost,
            opening_hours=opening,
            operational_status=OperationalStatus.unknown,
            children_suitable=True if child_tag else None,
            infants_suitable=None,
            source="knowledge_graph_postgres",
            fetched_at=fetched_at,
        )

    @staticmethod
    def _coordinates(latitude: Any, longitude: Any) -> Coordinates | None:
        try:
            if latitude in (None, "") or longitude in (None, ""):
                return None
            return Coordinates(latitude=float(latitude), longitude=float(longitude))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _integer(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _duration(value: Any) -> int | None:
        if not value:
            return None
        match = re.fullmatch(r"PT(\d+)M", str(value))
        return int(match.group(1)) if match else None

    @staticmethod
    def _opening_hours(values: dict[str, Any]) -> list[str] | None:
        windows = values.get("time_windows")
        if windows:
            try:
                parsed = json.loads(windows)
                result = [f"{item['start']}-{item['end']}" for item in parsed]
                if result:
                    return result
            except (TypeError, ValueError, KeyError):
                pass
        opened, closed = values.get("time_open"), values.get("time_close")
        return [f"{opened}-{closed}"] if opened and closed else None

    @staticmethod
    def _typical_cost(minimum: float | None, maximum: float | None) -> float | None:
        if minimum is None:
            return maximum
        if maximum is None:
            return minimum
        return (minimum + maximum) / 2

    @staticmethod
    def _cost_tier(maximum: float | None) -> CostTier:
        if maximum is None:
            return CostTier.unknown
        if maximum == 0:
            return CostTier.free
        if maximum <= 100_000:
            return CostTier.low
        if maximum <= 300_000:
            return CostTier.medium
        if maximum <= 700_000:
            return CostTier.high
        return CostTier.premium
