"""Ontology definitions for Knowledge Graph.

This module provides static definitions for node types, relationship types,
and their property requirements. These are derived from the CSV/YAML knowledge
graph package used by the travel domain.
"""

from typing import TypedDict


class NodeTypeProperties(TypedDict):
    requiredProperties: list[str]
    optionalProperties: list[str]


ONTOLOGY_NODE_TYPES = [
    "Area",
    "TravelPlace",
    "Restaurant",
    "DrinkDessert",
    "Accommodation",
    "Activity",
]

ONTOLOGY_RELATIONSHIP_TYPES = [
    "LOCATED_IN",
    "NEAR",
    "PART_OF",
    "CONNECTS_TO",
    "RECOMMENDS",
    "OFFERS_ACTIVITY",
    "SPECIAL_EXPERIENCE",
]

ONTOLOGY_NODE_TYPE_PROPERTIES: dict[str, NodeTypeProperties] = {
    "Area": {
        "requiredProperties": ["description", "latitude", "longitude"],
        "optionalProperties": ["country", "administrative_level", "timezone", "region", "special_experience"],
    },
    "TravelPlace": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "opening_hours",
            "phone",
            "official_website",
            "rating",
            "review_count",
            "facilities",
            "accessibility_features",
            "images",
            "source_category",
            "source_platform",
            "source_url",
            "plus_code",
            "place_category",
            "admission_fee_vnd",
            "ticket_options",
            "booking_required",
            "booking_url",
            "best_visit_months",
            "weather_constraints",
            "special_experience",
        ],
    },
    "Restaurant": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "opening_hours",
            "phone",
            "official_website",
            "rating",
            "review_count",
            "facilities",
            "accessibility_features",
            "images",
            "source_category",
            "source_platform",
            "source_url",
            "plus_code",
            "cuisine",
            "signature_dishes",
            "price_level",
            "special_experience",
        ],
    },
    "DrinkDessert": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "opening_hours",
            "phone",
            "official_website",
            "rating",
            "review_count",
            "facilities",
            "accessibility_features",
            "images",
            "source_category",
            "source_platform",
            "source_url",
            "plus_code",
            "specialties",
            "price_level",
            "special_experience",
        ],
    },
    "Accommodation": {
        "requiredProperties": ["description", "latitude", "longitude", "address"],
        "optionalProperties": [
            "opening_hours",
            "phone",
            "official_website",
            "rating",
            "review_count",
            "facilities",
            "accessibility_features",
            "images",
            "source_category",
            "source_platform",
            "source_url",
            "plus_code",
            "accommodation_type",
            "check_in_time",
            "check_out_time",
            "price_range_vnd",
            "special_experience",
        ],
    },
    "Activity": {
        "requiredProperties": ["description", "activity_category"],
        "optionalProperties": [
            "typical_duration_minutes",
            "best_time_slots",
            "suitable_for",
            "requirements",
            "booking_required",
            "special_experience",
        ],
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
