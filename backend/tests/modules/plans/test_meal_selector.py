from __future__ import annotations

from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.finder.place_tool import FinderPlace
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
) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
        placeType=place_type,
        regionKey="vn,ha-noi",
        tags=["food"],
        latitude=latitude,
        longitude=longitude,
    )


class _PlaceTool:
    def __init__(self, places: list[FinderPlace]) -> None:
        self.places = places

    def get(self, place_id: str) -> FinderPlace | None:
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
    ) -> list[FinderPlace]:
        del region_key, target_tags, bbox_filter
        return [
            place
            for place in self.places
            if place.place_id not in excluded_place_ids
        ][:limit]
