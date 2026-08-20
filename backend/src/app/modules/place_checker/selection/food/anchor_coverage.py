"""Measure restaurant proximity coverage for final activity anchors."""


def unpaired_activity_anchor_ids(places, food, entertainment) -> list[str]:
    anchors = [
        *places,
        *(item for item in entertainment if item.entity_type == "entertainment"),
    ]
    paired_ids = {
        related_id for restaurant in food for related_id in restaurant.relationships
    }
    return [item.place_id for item in anchors if item.place_id not in paired_ids]
