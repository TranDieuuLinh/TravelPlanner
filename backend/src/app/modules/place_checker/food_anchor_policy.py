from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.food_selection_contract import FoodSelectionAnchor


def select_food_anchors(
    evaluated: PlaceEvaluationBatch,
    *,
    days: int,
) -> list[FoodSelectionAnchor]:
    """Keep mandatory, high-ranked and geographically representative anchors."""
    eligible = [
        item
        for item in evaluated.places
        if item.planner_eligible
        and item.place.place_id
        and item.place.metadata
        and item.place.metadata.category == "travel_place"
    ]
    mandatory = [item for item in eligible if item.place.mandatory]
    optional = [item for item in eligible if not item.place.mandatory]
    target = max(len(mandatory), min(12, max(8, days * 2)))

    chosen = list(mandatory)
    top_ranked_count = min(3, max(0, target - len(chosen)))
    chosen.extend(optional[:top_ranked_count])
    remaining = optional[top_ranked_count:]

    while remaining and len(chosen) < target:
        with_coordinates = [
            item for item in remaining if item.place.metadata.coordinates is not None
        ]
        chosen_coordinates = [
            item.place.metadata.coordinates
            for item in chosen
            if item.place.metadata and item.place.metadata.coordinates is not None
        ]
        if not with_coordinates or not chosen_coordinates:
            selected = remaining[0]
        else:
            selected = max(
                with_coordinates,
                key=lambda item: (
                    min(
                        _distance_squared(item.place.metadata.coordinates, center)
                        for center in chosen_coordinates
                    ),
                    -eligible.index(item),
                ),
            )
        chosen.append(selected)
        remaining.remove(selected)

    return [
        FoodSelectionAnchor(
            place_id=item.place.place_id,
            name=(item.place.canonical_name or item.place.original_names[0]),
        )
        for item in chosen
    ]


def _distance_squared(left, right) -> float:
    latitude = left.latitude - right.latitude
    longitude = left.longitude - right.longitude
    return latitude * latitude + longitude * longitude
