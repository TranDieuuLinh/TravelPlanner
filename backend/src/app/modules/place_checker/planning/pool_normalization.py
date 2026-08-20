from __future__ import annotations

from app.modules.place_checker.selection.food.contract import SelectedFoodRestaurant
from app.modules.place_checker.output_contract import (
    PlannerOutputEntertainment,
    PlannerOutputFood,
    PlannerOutputPlace,
)
from app.modules.place_checker.planning.category import planner_category_for_candidate


def merge_selection_relationships(
    candidate: PlannerOutputFood | PlannerOutputEntertainment | PlannerOutputPlace,
    selection: SelectedFoodRestaurant,
) -> list[str]:
    return list(
        dict.fromkeys(
            [*candidate.relationships, *selection.related_anchor_place_ids]
        )
    )


def move_food_to_drink_entertainment(
    candidate: PlannerOutputFood,
    selection: SelectedFoodRestaurant,
) -> PlannerOutputEntertainment:
    return _drink_entertainment(
        candidate,
        relationships=merge_selection_relationships(candidate, selection),
    )


def move_place_to_drink_entertainment(
    candidate: PlannerOutputPlace,
    selection: SelectedFoodRestaurant,
) -> PlannerOutputEntertainment:
    return _drink_entertainment(
        candidate,
        relationships=merge_selection_relationships(candidate, selection),
    )


def move_existing_candidate_to_drink_entertainment(
    places: list[PlannerOutputPlace],
    food: list[PlannerOutputFood],
    entertainment: list[PlannerOutputEntertainment],
    place_id: str,
) -> bool:
    for candidates in (food, places):
        index = next(
            (
                index
                for index, candidate in enumerate(candidates)
                if candidate.place_id == place_id
            ),
            None,
        )
        if index is None:
            continue
        entertainment.append(_drink_entertainment(candidates.pop(index)))
        return True
    for index, candidate in enumerate(entertainment):
        if candidate.place_id == place_id:
            entertainment[index] = candidate.model_copy(
                update={"entity_type": "drink_dessert"}
            )
            return True
    return False


def _drink_entertainment(
    candidate: PlannerOutputPlace | PlannerOutputFood,
    *,
    relationships: list[str] | None = None,
) -> PlannerOutputEntertainment:
    excluded = (
        {"venue_type", "supported_meals"}
        if isinstance(candidate, PlannerOutputFood)
        else set()
    )
    return PlannerOutputEntertainment.model_validate(
        {
            **candidate.model_dump(exclude=excluded),
            "entity_type": "drink_dessert",
            "relationships": (
                candidate.relationships if relationships is None else relationships
            ),
        }
    )


def move_food_selection_if_drink(
    food: list[PlannerOutputFood],
    entertainment: list[PlannerOutputEntertainment],
    index: int,
    selection: SelectedFoodRestaurant,
) -> bool:
    category = planner_category_for_candidate(
        selection.metadata.category,
        name=selection.restaurant_name,
        tags=selection.metadata.tags,
    )
    if category != "drink_dessert":
        return False
    entertainment.append(move_food_to_drink_entertainment(food.pop(index), selection))
    return True


def move_place_selection_if_drink(
    places: list[PlannerOutputPlace],
    entertainment: list[PlannerOutputEntertainment],
    index: int,
    selection: SelectedFoodRestaurant,
) -> bool:
    category = planner_category_for_candidate(
        selection.metadata.category,
        name=selection.restaurant_name,
        tags=selection.metadata.tags,
    )
    if category != "drink_dessert":
        return False
    entertainment.append(
        move_place_to_drink_entertainment(places.pop(index), selection)
    )
    return True


def promote_user_input(candidates: list, place_id: str) -> list:
    return [
        candidate.model_copy(update={"priority": "user_input"})
        if candidate.place_id == place_id
        else candidate
        for candidate in candidates
    ]
