import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.modules.place_checker.enums import CostTier, OperationalStatus
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import AdministrativeArea, PlaceProviderCandidate
from app.shared.tools.search_places.normalization import normalize_text


PLACE_TYPES = {"TravelPlace", "Restaurant", "DrinkDessert", "Accommodation"}
TYPE_BY_HINT = {
    "travel place": {"TravelPlace"}, "attraction": {"TravelPlace"},
    "experience": {"TravelPlace"}, "restaurant": {"Restaurant"},
    "food": {"Restaurant"}, "food venue": {"Restaurant"},
    "cafe": {"DrinkDessert"}, "coffee": {"DrinkDessert"},
    "drink": {"DrinkDessert"}, "drink dessert": {"DrinkDessert"},
    "hotel": {"Accommodation"}, "accommodation": {"Accommodation"},
}
CANONICAL_TYPE = {
    "TravelPlace": "travel_place", "Restaurant": "restaurant",
    "DrinkDessert": "drink_dessert", "Accommodation": "accommodation",
}
TOURISM_EXPERIENCE_MARKERS = {
    "cam trai", "cuoi ngua", "di bo", "di dao", "ghe chua",
    "mua do luu niem", "ngam ", "qua cau", "tham ", "tham gia hoi cho",
    "tham quan", "trai nghiem van hoa", "vui choi danh cho tre em",
    "xem bieu dien nghe thuat",
}


class PostgresCatalogMappingMixin:
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
            for tag in tags if tag.startswith("experience:")
        ]
        return any(
            marker in experience
            for experience in experiences for marker in TOURISM_EXPERIENCE_MARKERS
        )

    @classmethod
    def _cap_tourism_experience_groups(
        cls, candidates: list[PlaceProviderCandidate], *, per_group: int = 2,
    ) -> list[PlaceProviderCandidate]:
        counts: dict[str, int] = defaultdict(int)
        selected = []
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
            for tag in tags if tag.startswith("experience:")
        ]
        if "special experience" in values:
            return "area_special"
        groups = (
            ("camping", ("cam trai",)), ("culture", ("van hoa", "tin nguong", "ghe chua")),
            ("landmark", ("dia danh", "ngam ", "qua cau")),
            ("outdoor_walk", ("di dao", "di bo")),
            ("family", ("vui choi danh cho tre em",)),
            ("performance", ("xem bieu dien",)), ("event", ("hoi cho",)),
            ("souvenir", ("do luu niem",)), ("horse_riding", ("cuoi ngua",)),
        )
        for group, markers in groups:
            if any(marker in value for marker in markers for value in values):
                return group
        return "other_tourism" if any(
            marker in value for value in values for marker in TOURISM_EXPERIENCE_MARKERS
        ) else None

    @staticmethod
    def _candidate(row, input_adm: AdministrativeArea) -> PlaceProviderCandidate:
        category = CANONICAL_TYPE.get(row["entity_type"], normalize_text(row["entity_type"]))
        rating = PostgresCatalogMappingMixin._number(row["rating"])
        confidence = 0.75 if rating is None else min(0.98, 0.65 + rating / 20)
        raw_tags = list(row["tags"] or [])
        relationships = PostgresCatalogMappingMixin._relationships(
            row["relationship_evidence"]
        )
        if row["anchor_relation"]:
            raw_tags.append(row["anchor_relation"])
        return PlaceProviderCandidate(
            provider="knowledge_graph", entity_id=row["id"], name=row["canonical_name"],
            aliases=list(row["aliases"] or []), address=row["address"],
            coordinates=PostgresCatalogMappingMixin._coordinates(row["latitude"], row["longitude"]),
            adm_ids=[input_adm.adm_id], adm_names=[input_adm.name],
            canonical_type=category, tags=list(dict.fromkeys([category.replace("_", " "), *raw_tags])),
            rating=rating, review_count=PostgresCatalogMappingMixin._integer(row["review_count"]),
            relationship_score=float(row["relationship_score"] or 0),
            relationship_evidence=[
                relationship.model_dump(by_alias=True) for relationship in relationships
            ],
            data_confidence=confidence, fetched_at=row["updated_at"],
        )

    @classmethod
    def _metadata(
        cls, place_id: str, entity_type: str, values: dict[str, Any],
        tags: list[str], fetched_at: datetime | None,
        relationships: list[PlaceRelationshipEvidence] | None = None,
    ) -> PlaceMetadata:
        relationships = relationships or []
        relationships = list(
            {
                (
                    relationship.relationship_type,
                    relationship.related_entity_id,
                    relationship.scope,
                ): relationship
                for relationship in sorted(
                    relationships,
                    key=lambda item: item.score,
                )
            }.values()
        )
        values = cls._with_style_defaults(values, relationships)
        minimum_cost = cls._number(values.get("price_min"))
        maximum_cost = cls._number(values.get("price_max"))
        duration = cls._duration(values.get("time_duration"))
        category = CANONICAL_TYPE.get(entity_type, normalize_text(entity_type))
        child_tag = any("vui chơi dành cho trẻ em" in tag.casefold() for tag in tags)
        return PlaceMetadata(
            place_id=place_id, coordinates=cls._coordinates(values.get("latitude"), values.get("longitude")),
            address=values.get("address"), category=category,
            tags=list(dict.fromkeys([category.replace("_", " "), *tags])),
            rating=cls._number(values.get("rating")), review_count=cls._integer(values.get("review_count")),
            minimum_duration_minutes=max(15, duration - 30) if duration else None,
            typical_duration_minutes=duration,
            maximum_duration_minutes=min(1440, duration + 30) if duration else None,
            cost_tier=cls._cost_tier(maximum_cost),
            cost_currency="VND" if minimum_cost is not None or maximum_cost is not None else None,
            minimum_cost=minimum_cost, typical_cost=cls._typical_cost(minimum_cost, maximum_cost),
            maximum_cost=maximum_cost, opening_hours=cls._opening_hours(values),
            operational_status=OperationalStatus.unknown,
            children_suitable=True if child_tag else None, infants_suitable=None,
            source="knowledge_graph_postgres", fetched_at=fetched_at,
            relationships=relationships,
        )

    @staticmethod
    def _relationships(value: Any) -> list[PlaceRelationshipEvidence]:
        if value in (None, ""):
            return []
        try:
            payload = json.loads(value) if isinstance(value, str) else value
            return [PlaceRelationshipEvidence.model_validate(item) for item in payload]
        except (TypeError, ValueError):
            return []

    @staticmethod
    def _with_style_defaults(
        values: dict[str, Any],
        relationships: list[PlaceRelationshipEvidence],
    ) -> dict[str, Any]:
        merged = dict(values)
        styles = sorted(
            (
                relationship
                for relationship in relationships
                if relationship.relationship_type == "Has_Style"
                and relationship.properties
            ),
            key=lambda relationship: relationship.priority or 0,
            reverse=True,
        )
        for relationship in styles:
            properties = relationship.properties
            if not merged.get("time_windows") and properties.get("time_windows"):
                merged["time_windows"] = json.dumps(properties["time_windows"])
            if not merged.get("time_duration") and properties.get("time_duration"):
                merged["time_duration"] = properties["time_duration"]
        return merged

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
        match = re.fullmatch(r"PT(\d+)M", str(value)) if value else None
        return int(match.group(1)) if match else None

    @staticmethod
    def _opening_hours(values: dict[str, Any]) -> list[str] | None:
        if values.get("time_windows"):
            try:
                result = [
                    f"{item['start']}-{item['end']}"
                    for item in json.loads(values["time_windows"])
                ]
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
