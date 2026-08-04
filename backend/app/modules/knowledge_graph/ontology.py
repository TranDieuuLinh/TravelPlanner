"""Ontology definitions for Knowledge Graph.

This module provides static definitions for node types, relationship types,
and their property requirements. These are derived from the travel domain schema.
"""

from typing import TypedDict


class NodeTypeProperties(TypedDict):
    requiredProperties: list[str]
    optionalProperties: list[str]


ONTOLOGY_NODE_TYPES = [
    "Area",
    "City",
    "District",
    "TravelPlace",
    "Restaurant",
    "DrinkDessert",
    "Accommodation",
    "Activity",
]

ONTOLOGY_RELATIONSHIP_TYPES = [
    "is_in_area",
    "is_in_city",
    "is_in_district",
    "has_place",
    "has_restaurant",
    "has_activity",
    "has_accommodation",
    "serves_food",
    "located_in",
]

ONTOLOGY_NODE_TYPE_PROPERTIES: dict[str, NodeTypeProperties] = {
    "Area": {
        "requiredProperties": ["name", "country"],
        "optionalProperties": ["description", "best_time_to_visit"],
    },
    "City": {
        "requiredProperties": ["name", "country"],
        "optionalProperties": ["population", "description", "best_time_to_visit"],
    },
    "District": {
        "requiredProperties": ["name"],
        "optionalProperties": ["description"],
    },
    "TravelPlace": {
        "requiredProperties": ["name", "type"],
        "optionalProperties": ["address", "description", "opening_hours", "price_level", "rating"],
    },
    "Restaurant": {
        "requiredProperties": ["name", "cuisine_type"],
        "optionalProperties": ["address", "price_range", "opening_hours", "rating"],
    },
    "DrinkDessert": {
        "requiredProperties": ["name"],
        "optionalProperties": ["type", "description", "price_range"],
    },
    "Accommodation": {
        "requiredProperties": ["name", "type"],
        "optionalProperties": ["address", "price_range", "rating", "amenities"],
    },
    "Activity": {
        "requiredProperties": ["name"],
        "optionalProperties": ["description", "duration", "price_range", "best_time"],
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
