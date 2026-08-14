from __future__ import annotations

import json
from typing import Any, Literal

from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence


SourceKind = Literal["special_experience", "offer_item", "both", "generic"]
TimeSource = Literal[
    "place", "activity_item", "has_style", "source_hint", "unknown"
]


def source_metadata(
    relationships: list[PlaceRelationshipEvidence],
) -> tuple[SourceKind, list[str]]:
    special = any(
        relation.relationship_type == "Special_Experience"
        for relation in relationships
    )
    activity_ids = list(
        dict.fromkeys(
            relation.related_entity_id or relation.to_entity_id
            for relation in relationships
            if _is_activity_offer(relation)
        )
    )
    if special and activity_ids:
        return "both", activity_ids
    if special:
        return "special_experience", []
    if activity_ids:
        return "offer_item", activity_ids
    return "generic", []


def preferred_time_values(
    *,
    direct_values: list[str],
    relationships: list[PlaceRelationshipEvidence],
) -> tuple[list[str], TimeSource]:
    if direct_values:
        return direct_values, "source_hint"
    activity_values = _relationship_windows(relationships, "Offer_Item")
    if activity_values:
        return activity_values, "activity_item"
    style_values = _relationship_windows(relationships, "Has_Style")
    if style_values:
        return style_values, "has_style"
    return [], "unknown"


def time_source(
    *,
    direct_values: list[str],
    opening_hours: list[str] | None,
    relationships: list[PlaceRelationshipEvidence],
) -> TimeSource:
    _, preferred_source = preferred_time_values(
        direct_values=direct_values,
        relationships=relationships,
    )
    if preferred_source != "unknown":
        return preferred_source
    return "place" if opening_hours else "unknown"


def _is_activity_offer(relation: PlaceRelationshipEvidence) -> bool:
    if relation.relationship_type != "Offer_Item":
        return False
    entity_type = str(
        relation.properties.get("entityType")
        or relation.properties.get("entity_type")
        or ""
    ).casefold()
    return entity_type == "activityitem"


def _relationship_windows(
    relationships: list[PlaceRelationshipEvidence],
    relationship_type: str,
) -> list[str]:
    result: list[str] = []
    for relation in relationships:
        if relation.relationship_type != relationship_type:
            continue
        if relationship_type == "Offer_Item" and not _is_activity_offer(relation):
            continue
        raw = relation.properties.get("time_windows")
        if raw is None:
            raw = relation.properties.get("timeWindows")
        for item in _window_items(raw):
            start, end = item.get("start"), item.get("end")
            if start and end:
                value = f"{start}-{end}"
                if value not in result:
                    result.append(value)
    return result


def _window_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
