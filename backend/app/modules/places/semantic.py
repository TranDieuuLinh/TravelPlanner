from __future__ import annotations

import hashlib
import json

from app.modules.places.model import Place
from app.modules.plans.planner.place_metadata import read_description, read_tags


PLACE_EMBEDDING_CONTENT_VERSION = "place_document_v1"


def build_place_embedding_text(place: Place) -> str:
    """Build stable, provenance-safe text used for semantic place retrieval."""

    metadata = place.metadata_json or {}
    values = {
        "name": place.name,
        "placeType": place.place_type,
        "placeGroup": metadata.get("placeGroup") or metadata.get("place_group"),
        "description": read_description(place),
        "tags": read_tags(place),
        "address": place.address,
        "primaryArea": place.primary_area,
        "city": place.city,
        "regionKey": place.region_key,
    }
    lines = [
        "Tourism place for itinerary recommendation.",
        *(f"{key}: {value}" for key, value in values.items() if value not in (None, "", [])),
    ]
    return "\n".join(lines)


def place_embedding_content_hash(place: Place) -> str:
    payload = {
        "version": PLACE_EMBEDDING_CONTENT_VERSION,
        "text": build_place_embedding_text(place),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_finder_query_text(
    *,
    target_tags: list[str],
    query_categories: set[str],
    region_key: str,
) -> str:
    categories = ", ".join(sorted(query_categories)) or "travel place"
    goals = "; ".join(value.strip() for value in target_tags if value.strip())
    return (
        "Find a tourism place suitable for this itinerary block.\n"
        f"Destination region: {region_key}\n"
        f"Required category: {categories}\n"
        f"Traveler goal and local context: {goals}"
    )
