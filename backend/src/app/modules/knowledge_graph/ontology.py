from typing import TypedDict


class NodeTypeProperties(TypedDict):
    requiredProperties: list[str]
    optionalProperties: list[str]


class RelationshipEndpointRule(TypedDict):
    fromTypes: list[str]
    toTypes: list[str]


# This mirrors the concrete node types in
# trung-plans/plans-for-new-version/knowledge/schema.yml. Abstract parents are
# merged into each concrete node type so the frontend receives one usable shape.
ENTITY_REQUIRED = ["id", "name", "type"]
ENTITY_OPTIONAL = [
    "description",
    "tags",
    "fetch_at",
    "verify_by",
    "source_note",
    "meta_json",
    "note",
]
REGION_OPTIONAL = ENTITY_OPTIONAL + ["story"]
PLACE_REQUIRED = ENTITY_REQUIRED + ["latitude", "longitude"]
PLACE_OPTIONAL = ENTITY_OPTIONAL + [
    "rating",
    "review_count",
    "address",
    "phone",
    "url_google_map",
    "google_place_id",
    "website",
    "time_open",
    "time_close",
    "time_windows",
    "time_duration",
    "price_min",
    "price_max",
    "image",
    "story",
    "icon",
]
ITEM_OPTIONAL = ENTITY_OPTIONAL + [
    "rating",
    "review_count",
    "price_min",
    "price_max",
    "image",
    "story",
]
ACTIVITY_OPTIONAL = ENTITY_OPTIONAL + [
    "time_windows",
    "time_duration",
    "price_min",
    "price_max",
    "story",
    "image",
]
STYLE_OPTIONAL = ENTITY_OPTIONAL + ["style_group", "time_windows", "time_duration", "story"]
ITEM_TYPES = ["ActivityItem", "DrinkItem", "FoodItem", "ProductItem"]
OFFER_ITEM_SOURCE_TYPES = [
    "ADM0",
    "ADM1",
    "ADM2",
    "Accommodation",
    "DrinkDessert",
    "Entertainment",
    "Restaurant",
    "SubPlace",
    "TravelPlace",
]

NODE_TYPES = [
    "ADM0",
    "ADM1",
    "ADM2",
    "Accommodation",
    "ActivityItem",
    "DrinkDessert",
    "DrinkItem",
    "Entertainment",
    "FoodItem",
    "ProductItem",
    "Restaurant",
    "Style",
    "SubPlace",
    "TravelPlace",
]

RELATIONSHIP_TYPES = [
    "Adjacent_To",
    "Located_In",
    "Offer_Item",
    "Has_Style",
    "Has_Subplace",
    "Special_Experience",
    "Special_Near",
    "Near",
    "Must_Visit",
]

RELATIONSHIP_ENDPOINT_RULES: dict[str, RelationshipEndpointRule] = {
    "Has_Subplace": {
        "fromTypes": ["TravelPlace"],
        "toTypes": ["SubPlace"],
    },
    "Offer_Item": {
        "fromTypes": OFFER_ITEM_SOURCE_TYPES,
        "toTypes": ITEM_TYPES,
    },
}

PROPERTY_KEYS = [
    "id",
    "name",
    "type",
    "description",
    "tags",
    "rating",
    "review_count",
    "latitude",
    "longitude",
    "address",
    "phone",
    "url_google_map",
    "google_place_id",
    "website",
    "time_open",
    "time_close",
    "time_windows",
    "time_duration",
    "price_min",
    "price_max",
    "fetch_at",
    "verify_by",
    "story",
    "meta_json",
    "image",
    "source_note",
    "menu_urls",
    "icon",
    "note",
    "style_group",
]

NODE_TYPE_PROPERTIES: dict[str, NodeTypeProperties] = {
    node_type: {"requiredProperties": ENTITY_REQUIRED, "optionalProperties": REGION_OPTIONAL}
    for node_type in ["ADM0", "ADM1", "ADM2"]
}
NODE_TYPE_PROPERTIES.update(
    {
        node_type: {"requiredProperties": PLACE_REQUIRED, "optionalProperties": PLACE_OPTIONAL}
        for node_type in ["Accommodation", "TravelPlace"]
    }
)
NODE_TYPE_PROPERTIES["Entertainment"] = {
    "requiredProperties": PLACE_REQUIRED,
    "optionalProperties": PLACE_OPTIONAL,
}
NODE_TYPE_PROPERTIES.update(
    {
        node_type: {
            "requiredProperties": PLACE_REQUIRED,
            "optionalProperties": PLACE_OPTIONAL + ["menu_urls"],
        }
        for node_type in ["Restaurant", "DrinkDessert"]
    }
)
NODE_TYPE_PROPERTIES.update(
    {
        node_type: {"requiredProperties": ENTITY_REQUIRED, "optionalProperties": ITEM_OPTIONAL}
        for node_type in ["FoodItem", "DrinkItem", "ProductItem"]
    }
)
NODE_TYPE_PROPERTIES["ActivityItem"] = {
    "requiredProperties": ENTITY_REQUIRED,
    "optionalProperties": ACTIVITY_OPTIONAL,
}
NODE_TYPE_PROPERTIES["Style"] = {
    "requiredProperties": ENTITY_REQUIRED,
    "optionalProperties": STYLE_OPTIONAL,
}
NODE_TYPE_PROPERTIES["SubPlace"] = {
    "requiredProperties": PLACE_REQUIRED,
    "optionalProperties": PLACE_OPTIONAL,
}


def ontology_payload() -> dict[str, object]:
    return {
        "nodeTypes": NODE_TYPES,
        "propertyKeys": PROPERTY_KEYS,
        "relationshipTypes": RELATIONSHIP_TYPES,
        "relationshipEndpointRules": RELATIONSHIP_ENDPOINT_RULES,
        "nodeTypeProperties": NODE_TYPE_PROPERTIES,
    }
