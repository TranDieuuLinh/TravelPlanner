from __future__ import annotations

from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.meal_selector import MealStopSelector


def test_meals_are_selected_after_activities_using_route_anchors() -> None:
    places = [
        _food("breakfast", "Breakfast bakery", 21.03, 105.8005, "bakery"),
        _food("lunch", "Lunch restaurant", 21.03, 105.81, "restaurant"),
        _food("dinner", "Dinner restaurant", 21.03, 105.8195, "restaurant"),
    ]
    selector = MealStopSelector(_PlaceTool(places))

    selected = selector.select_for_day(
        region_key="vn,ha-noi",
        activities=[
            _activity("activity-1", 21.03, 105.80),
            _activity("activity-2", 21.03, 105.82),
        ],
        excluded_place_ids={"activity-1", "activity-2"},
    )

    assert selected["breakfast_meal"].place_id == "breakfast"
    assert selected["lunch_meal"].place_id == "lunch"
    assert selected["dinner_meal"].place_id == "dinner"
    assert len({place.place_id for place in selected.values() if place}) == 3


def test_meal_relevance_is_decided_before_route_distance() -> None:
    selector = MealStopSelector(_PlaceTool([]))
    first = _activity("activity-1", 21.03, 105.80)
    second = _activity("activity-2", 21.03, 105.82)
    far_relevant = _food(
        "far-local-lunch",
        "Local lunch specialist",
        21.07,
        105.88,
        "restaurant",
    ).model_copy(update={"tags": ["lunch", "local food"]})
    near_generic = _food(
        "near-generic",
        "Generic restaurant",
        21.03,
        105.81,
        "restaurant",
    )

    chosen = selector._choose(
        [far_relevant, near_generic],
        role="lunch_meal",
        first=first,
        second=second,
        region_key="vn,ha-noi",
        target_tags=["lunch", "local food", "restaurant"],
    )

    assert chosen is not None
    assert chosen.place_id == "far-local-lunch"


def test_meal_selector_rejects_food_suppliers_stores_and_schools() -> None:
    places = [
        _food("supplier", "Drink supplier", 21.03, 105.801, "Catering food and drink supplier"),
        _food("store", "Organic store", 21.03, 105.802, "Organic food store"),
        _food("school", "Cooking school", 21.03, 105.803, "Culinary school"),
        _food("restaurant", "Actual restaurant", 21.03, 105.804, "Vietnamese restaurant"),
    ]
    selector = MealStopSelector(_PlaceTool(places))

    candidates = selector._candidates(
        region_key="vn,ha-noi",
        target_tags=["local food", "restaurant"],
        excluded_place_ids=set(),
        bbox_filter=None,
    )

    assert [candidate.place_id for candidate in candidates] == ["restaurant"]


def test_meal_selector_uses_at_most_one_coffee_venue_per_day() -> None:
    places = [
        _food("coffee-one", "Coffee one", 21.03, 105.801, "Cafe"),
        _food("coffee-two", "Coffee two", 21.03, 105.802, "Coffee shop"),
        _food("restaurant-one", "Restaurant one", 21.03, 105.803, "Restaurant"),
        _food("restaurant-two", "Restaurant two", 21.03, 105.804, "Restaurant"),
    ]
    selector = MealStopSelector(_PlaceTool(places))

    selected = selector.select_for_day(
        region_key="vn,ha-noi",
        activities=[
            _activity("activity-1", 21.03, 105.80),
            _activity("activity-2", 21.03, 105.82),
        ],
        excluded_place_ids={"activity-1", "activity-2"},
    )

    assert sum(
        place is not None and "coffee" in place.name.casefold()
        for place in selected.values()
    ) <= 1


def test_meals_are_bounded_by_activity_radius_before_quality_ranking() -> None:
    places = [
        _food("near", "Near restaurant", 21.03, 105.801, "restaurant").model_copy(
            update={"rating": 4.2, "reviewCount": 40}
        ),
        _food("far", "Far restaurant", 21.08, 105.88, "restaurant").model_copy(
            update={"rating": 4.9, "reviewCount": 5000}
        ),
    ]
    selector = MealStopSelector(_PlaceTool(places))

    selected = selector.select_for_day(
        region_key="vn,ha-noi",
        activities=[
            _activity("activity-1", 21.03, 105.80),
            _activity("activity-2", 21.03, 105.82),
        ],
        excluded_place_ids={"activity-1", "activity-2"},
    )

    assert selected["breakfast_meal"] is not None
    assert selected["breakfast_meal"].place_id == "near"


def _activity(place_id: str, latitude: float, longitude: float) -> PlanItem:
    return PlanItem(
        placeId=place_id,
        name=place_id,
        timeWindow="00:00-00:01",
        placeType="attraction",
        timelineCategory="activity",
        latitude=latitude,
        longitude=longitude,
    )


def _food(
    place_id: str,
    name: str,
    latitude: float,
    longitude: float,
    place_type: str,
) -> SelectablePlace:
    return SelectablePlace(
        placeId=place_id,
        name=name,
        placeType=place_type,
        regionKey="vn,ha-noi",
        tags=["food"],
        latitude=latitude,
        longitude=longitude,
    )


class _PlaceTool:
    def __init__(self, places: list[SelectablePlace]) -> None:
        self.places = places

    def get(self, place_id: str) -> SelectablePlace | None:
        return next(
            (place for place in self.places if place.place_id == place_id),
            None,
        )

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[SelectablePlace]:
        del region_key, target_tags, bbox_filter
        return [
            place
            for place in self.places
            if place.place_id not in excluded_place_ids
        ][:limit]
