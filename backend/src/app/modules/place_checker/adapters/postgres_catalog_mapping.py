import json
import re
from datetime import datetime
from typing import Any

from app.modules.place_checker.enums import CostTier, OperationalStatus
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.shared.contracts.place import Coordinates
from app.shared.contracts.source_note import SourceNote
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


class PostgresCatalogMappingMixin:
    @staticmethod
    def _types_for_hint(place_type_hint: str | None) -> set[str]:
        if not place_type_hint:
            return PLACE_TYPES
        return TYPE_BY_HINT.get(normalize_text(place_type_hint), PLACE_TYPES)

    @staticmethod
    def _candidate(row, input_adm: AdministrativeArea) -> PlaceProviderCandidate:
        category = CANONICAL_TYPE.get(
            row["entity_type"], normalize_text(row["entity_type"])
        )
        rating = PostgresCatalogMappingMixin._number(row["rating"])
        confidence = 0.75 if rating is None else min(0.98, 0.65 + rating / 20)
        raw_tags = list(row["tags"] or [])
        relationships = PostgresCatalogMappingMixin._relationships(
            row["relationship_evidence"]
        )
        if row["anchor_relation"]:
            raw_tags.append(row["anchor_relation"])
        return PlaceProviderCandidate(
            provider="knowledge_graph",
            entity_id=row["id"],
            name=row["canonical_name"],
            aliases=list(row["aliases"] or []),
            address=row["address"],
            coordinates=PostgresCatalogMappingMixin._coordinates(
                row["latitude"], row["longitude"]
            ),
            adm_ids=[input_adm.adm_id],
            adm_names=[input_adm.name],
            canonical_type=category,
            tags=list(dict.fromkeys([category.replace("_", " "), *raw_tags])),
            rating=rating,
            review_count=PostgresCatalogMappingMixin._integer(row["review_count"]),
            relationship_score=float(row["relationship_score"] or 0),
            relationship_evidence=[
                relationship.model_dump(by_alias=True) for relationship in relationships
            ],
            data_confidence=confidence,
            fetched_at=row["updated_at"],
            verification_status=(
                "not_verified" if row["requires_admin_review"] else "verified"
            ),
        )

    @classmethod
    def _metadata(
        cls,
        place_id: str,
        entity_type: str,
        values: dict[str, Any],
        tags: list[str],
        fetched_at: datetime | None,
        relationships: list[PlaceRelationshipEvidence] | None = None,
    ) -> PlaceMetadata:
        relationships = relationships or []
        relationships = list(
            {
                (
                    relationship.relationship_type,
                    relationship.related_entity_id or relationship.to_entity_id,
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
        all_tags = list(
            dict.fromkeys(
                [
                    category.replace("_", " "),
                    *cls._property_tags(values.get("tags")),
                    *tags,
                ]
            )
        )
        child_tag = any(
            "vui chơi dành cho trẻ em" in tag.casefold() for tag in all_tags
        )
        return PlaceMetadata(
            place_id=place_id,
            coordinates=cls._coordinates(
                values.get("latitude"), values.get("longitude")
            ),
            address=values.get("address"),
            category=category,
            tags=all_tags,
            image_urls=cls._image_urls(values),
            rating=cls._number(values.get("rating")),
            review_count=cls._integer(values.get("review_count")),
            source_note=cls._source_note(values),
            minimum_duration_minutes=max(15, duration - 30) if duration else None,
            typical_duration_minutes=duration,
            maximum_duration_minutes=min(1440, duration + 30) if duration else None,
            cost_tier=cls._cost_tier(maximum_cost),
            cost_currency="VND"
            if minimum_cost is not None or maximum_cost is not None
            else None,
            minimum_cost=minimum_cost,
            typical_cost=cls._typical_cost(minimum_cost, maximum_cost),
            maximum_cost=maximum_cost,
            opening_hours=cls._opening_hours(values),
            operational_status=OperationalStatus.unknown,
            children_suitable=True if child_tag else None,
            infants_suitable=None,
            source="knowledge_graph_postgres",
            fetched_at=fetched_at,
            relationships=relationships,
        )

    @staticmethod
    def _source_note(values: dict[str, Any]) -> SourceNote | None:
        description = values.get("description")
        text = str(description).strip() if description not in (None, "") else ""
        if not text:
            return None
        source_url_value = values.get("url_google_map")
        source_url = (
            str(source_url_value).strip()
            if source_url_value not in (None, "")
            else None
        )
        return SourceNote(
            text=text,
            source_type="google_maps" if source_url else "knowledge_graph",
            source_url=source_url,
        )

    @staticmethod
    def _image_urls(values: dict[str, Any]) -> list[str]:
        """Normalize the supported Knowledge Graph image properties."""
        raw_values = [
            values.get(key)
            for key in (
                "image_urls",
                "imageUrls",
                "images",
                "image_url",
                "imageUrl",
                "image",
            )
            if values.get(key) not in (None, "")
        ]
        urls: list[str] = []
        pending = list(raw_values)
        while pending:
            value = pending.pop(0)
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                except (TypeError, ValueError):
                    parsed = stripped
                if parsed != stripped:
                    pending.insert(0, parsed)
                elif stripped.startswith(("https://", "http://")):
                    urls.append(stripped)
            elif isinstance(value, list):
                pending[:0] = value
            elif isinstance(value, dict):
                pending[:0] = [
                    value.get(key)
                    for key in ("url", "image_url", "imageUrl", "src")
                    if value.get(key)
                ]
        return list(dict.fromkeys(urls))

    @staticmethod
    def _property_tags(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        parsed = value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                parsed = re.split(r"[,;]", value)
        if not isinstance(parsed, list):
            parsed = [parsed]
        return list(dict.fromkeys(tag for item in parsed if (tag := str(item).strip())))

    @staticmethod
    def _relationships(value: Any) -> list[PlaceRelationshipEvidence]:
        if value in (None, ""):
            return []
        try:
            payload = json.loads(value) if isinstance(value, str) else value
            return [PlaceRelationshipEvidence.model_validate(item) for item in payload]
        except (TypeError, ValueError):
            return []

    @classmethod
    def _with_style_defaults(
        cls,
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
        style_windows: list[dict[str, Any]] = []
        style_durations: list[int] = []
        for relationship in styles:
            properties = relationship.properties
            if properties.get("time_windows"):
                raw_windows = properties["time_windows"]
                try:
                    parsed_windows = (
                        json.loads(raw_windows)
                        if isinstance(raw_windows, str)
                        else raw_windows
                    )
                except (TypeError, ValueError):
                    parsed_windows = []
                for window in (
                    parsed_windows if isinstance(parsed_windows, list) else []
                ):
                    if isinstance(window, dict) and window not in style_windows:
                        style_windows.append(window)
            if duration := cls._duration(properties.get("time_duration")):
                style_durations.append(duration)
        if not merged.get("time_windows") and style_windows:
            merged["time_windows"] = json.dumps(style_windows)
        if not merged.get("time_duration") and style_durations:
            merged["time_duration"] = f"PT{max(style_durations)}M"
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
