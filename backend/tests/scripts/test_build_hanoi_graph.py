from __future__ import annotations

import csv
from pathlib import Path

from backend.scripts.knowledge_graph.build_hanoi_graph import (
    ACTIVITY_SOURCE,
    SPECIAL_EXPERIENCE_SOURCE,
    build_rows,
    classify_place,
    infer_activity,
    validate,
)


def test_taxonomy_classifies_common_places_and_activities() -> None:
    assert classify_place("Pho restaurant") == "Restaurant"
    assert infer_activity("Pho restaurant", "Restaurant") == "eat_pho"
    assert classify_place("Coffee shop") == "DrinkDessert"
    assert infer_activity("Coffee shop", "DrinkDessert") == "drink_coffee"
    assert classify_place("Hotel") == "Accommodation"
    assert infer_activity("Hotel", "Accommodation") == "stay"
    assert infer_activity("Buddhist temple", "TravelPlace") == "cultural_visit"


def test_build_keeps_places_draft_and_auto_approves_activity(tmp_path: Path) -> None:
    places = tmp_path / "places.csv"
    fields = [
        "place_id", "title", "category", "description", "latitude", "longitude",
        "address", "borough", "city", "state", "country", "plus_code", "rating",
        "review_count", "source_platform", "source_link",
    ]
    with places.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({
            "place_id": "google-1",
            "title": "Phở thử nghiệm",
            "category": "Pho restaurant",
            "description": "",
            "latitude": "21.02",
            "longitude": "105.84",
            "address": "1 Phố Test, Hà Nội, Vietnam",
            "city": "Ha Noi",
            "country": "VN",
            "rating": "4.5",
            "review_count": "10",
            "source_platform": "google_maps",
            "source_link": "https://maps.example/place/1",
        })

    rows = build_rows(places)
    entities = {row["id"]: row for row in rows["entities"]}
    place = next(row for row in entities.values() if row["type"] == "Restaurant")
    activity = entities["activity_eat_pho"]
    assert place["status"] == "draft"
    assert activity["status"] == "verified"
    edge = next(
        row for row in rows["relationships"]
        if row["relationship"] == "OFFERS_ACTIVITY"
    )
    assert edge["source"] == ACTIVITY_SOURCE
    assert '"priority":"recommended"' in edge["recommendations"]
    assert '"start":"06:30"' in edge["recommendations"]
    located_edge = next(
        row for row in rows["relationships"]
        if row["relationship"] == "LOCATED_IN"
    )
    assert located_edge["recommendations"] == "[]"
    properties = {
        (row["entity_id"], row["key"]): row
        for row in rows["properties"]
    }
    special = properties[(place["id"], "special_experience")]
    assert special["source"] == SPECIAL_EXPERIENCE_SOURCE
    assert '"recommendedItems":["Phở"]' in special["value"]
    area = next(row for row in entities.values() if row["type"] == "Area")
    assert (area["id"], "special_experience") not in properties
    aliases = {
        (row["entity_id"], row["alias"])
        for row in rows["aliases"]
    }
    assert (place["id"], "Pho thu nghiem") in aliases
    assert (activity["id"], "Phở") in aliases
    assert (area["id"], "Hanoi") in aliases
    assert all(alias != entities[entity_id]["name"] for entity_id, alias in aliases)

    schema = {
        "nodes": ["TravelPlace", "Restaurant", "DrinkDessert", "Accommodation", "Area", "Activity"],
        "property_definitions": {
            key: {}
            for key in (
                "description", "latitude", "longitude", "address", "rating",
                "review_count", "source_platform", "source_url", "source_category",
                "place_category", "accommodation_type", "administrative_level",
                "country", "activity_category", "special_experience",
                "best_time_slots", "typical_duration_minutes",
            )
        },
    }
    assert validate(rows, schema) == []
