"""Ontology definitions for Knowledge Graph.

This module provides static definitions for node types, relationship types,
and their property requirements. These are derived from the CSV/YAML knowledge
graph package used by the travel domain.
"""

import re
import unicodedata
from typing import Literal, TypeAlias, TypedDict


KnowledgePlaceType: TypeAlias = Literal[
    "TravelPlace",
    "Restaurant",
    "DrinkDessert",
    "Accommodation",
]


def canonical_place_node_type(value: str | None) -> KnowledgePlaceType:
    """Normalize provider/legacy labels to the canonical place ontology."""
    decomposed = unicodedata.normalize("NFD", (value or "").casefold())
    normalized = "_".join(
        re.findall(
            r"[a-z0-9]+",
            "".join(
                character
                for character in decomposed
                if unicodedata.category(character) != "Mn"
            ).replace("đ", "d"),
        )
    )
    padded = f"_{normalized}_"
    if normalized in {"drinkdessert", "drink_dessert", "cafe"} or any(
        f"_{marker}_" in padded
        for marker in (
            "coffee",
            "bakery",
            "cake",
            "dessert",
            "ice_cream",
            "gelato",
            "bingsu",
            "che",
            "tea",
            "juice",
            "snack",
        )
    ):
        return "DrinkDessert"
    if normalized == "restaurant" or any(
        f"_{marker}_" in padded
        for marker in (
            "restaurant",
            "nha_hang",
            "quan_an",
            "fast_food",
            "food_court",
            "meal_takeaway",
            "seafood",
            "pho",
            "bun",
            "com",
            "mien",
            "chao",
            "hu_tieu",
            "mi_quang",
            "banh_mi",
            "lau",
        )
    ):
        return "Restaurant"
    if normalized in {"accommodation", "hotel"} or any(
        f"_{marker}_" in padded
        for marker in ("homestay", "hostel", "motel", "resort", "lodging")
    ):
        return "Accommodation"
    return "TravelPlace"


class NodeTypeProperties(TypedDict):
    requiredProperties: list[str]
    optionalProperties: list[str]


ONTOLOGY_NODE_TYPES = [
    "TravelPlace",
    "Restaurant",
    "DrinkDessert",
    "Accommodation",
    "Area",
    "Activity",
    "FoodItem",
    "DrinkItem",
    "ProductItem",
]

ONTOLOGY_RELATIONSHIP_TYPES = [
    "LOCATED_IN",
    "ADJACENT_TO",
    "PART_OF",
    "OFFERS_ACTIVITY",
    "SPECIAL_EXPERIENCE",
    "INVOLVES_ITEM",
    "OFFERS_ITEM",
    "TARGETS_PLACE",
]

PLACE_RUNTIME_PROPERTIES = [
    "region_key",
    "place_type",
    "city",
    "country",
    "country_code",
    "primary_area",
    "catalog_status",
    "data_confidence",
    "plus_code",
    "typical_duration_minutes",
    "source_fetched_at",
    "revision",
    "metadata",
]

ONTOLOGY_NODE_TYPE_PROPERTIES: dict[str, NodeTypeProperties] = {
    "Area": {
        "requiredProperties": ["description"],
        "optionalProperties": [
            "latitude",
            "longitude",
            "administrative_level",
            "country",
        ],
    },
    "TravelPlace": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "rating",
            "review_count",
            "source_category",
            "source_platform",
            "source_url",
            "place_category",
            "special_experience",
            "opening_hours",
            "admission_price",
            *PLACE_RUNTIME_PROPERTIES,
        ],
    },
    "Restaurant": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "rating",
            "review_count",
            "source_category",
            "source_platform",
            "source_url",
            "cuisine",
            "special_experience",
            "opening_hours",
            *PLACE_RUNTIME_PROPERTIES,
        ],
    },
    "DrinkDessert": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "rating",
            "review_count",
            "source_category",
            "source_platform",
            "source_url",
            "beverage_category",
            "special_experience",
            "opening_hours",
            *PLACE_RUNTIME_PROPERTIES,
        ],
    },
    "Accommodation": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "rating",
            "review_count",
            "source_category",
            "source_platform",
            "source_url",
            "accommodation_type",
            "special_experience",
            "opening_hours",
            *PLACE_RUNTIME_PROPERTIES,
        ],
    },
    "Activity": {
        "requiredProperties": ["description", "activity_category"],
        "optionalProperties": [
            "typical_duration_minutes",
            "best_time_slots",
            "special_experience",
        ],
    },
    "FoodItem": {
        "requiredProperties": ["description", "item_category"],
        "optionalProperties": ["cuisine", "dietary_tags"],
    },
    "DrinkItem": {
        "requiredProperties": ["description", "item_category"],
        "optionalProperties": ["beverage_category", "dietary_tags"],
    },
    "ProductItem": {
        "requiredProperties": ["description", "item_category"],
        "optionalProperties": ["product_category"],
    },
}


def get_node_types() -> list[str]:
    """Return sorted list of allowed node types."""
    return sorted(ONTOLOGY_NODE_TYPES)


def get_relationship_types() -> list[str]:
    """Return sorted list of allowed relationship types."""
    return sorted(ONTOLOGY_RELATIONSHIP_TYPES)


def get_node_type_properties(node_type: str) -> NodeTypeProperties:
    """Return property definitions for a node type."""
    return ONTOLOGY_NODE_TYPE_PROPERTIES.get(
        node_type,
        {"requiredProperties": [], "optionalProperties": []}
    )


def get_all_node_type_properties() -> dict[str, NodeTypeProperties]:
    """Return all node type property definitions."""
    return {
        node_type: get_node_type_properties(node_type)
        for node_type in ONTOLOGY_NODE_TYPES
    }
