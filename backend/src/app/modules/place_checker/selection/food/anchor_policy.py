from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.selection.food.contract import FoodSelectionAnchor
from app.modules.place_checker.planning.category import planner_category_for_candidate


FOOD_ANCHOR_CATEGORIES = frozenset({"travel_place", "entertainment"})


def select_food_anchors(
    evaluated: PlaceEvaluationBatch,
    *,
    days: int,
) -> list[FoodSelectionAnchor]:
    """Use actual eligible TravelPlace and Entertainment venues as anchors."""
    del days  # Pool size does not change which real itinerary places are anchors.
    anchors: list[FoodSelectionAnchor] = []
    seen: set[str] = set()
    for item in evaluated.places:
        place = item.place
        metadata = place.metadata
        if (
            not item.planner_eligible
            or not place.place_id
            or metadata is None
            or metadata.coordinates is None
            or place.place_id in seen
        ):
            continue
        category = planner_category_for_candidate(
            metadata.category,
            name=place.canonical_name,
            tags=metadata.tags,
        )
        if category not in FOOD_ANCHOR_CATEGORIES:
            continue
        anchors.append(
            FoodSelectionAnchor(
                place_id=place.place_id,
                name=place.canonical_name or place.original_names[0],
            )
        )
        seen.add(place.place_id)
    return anchors
