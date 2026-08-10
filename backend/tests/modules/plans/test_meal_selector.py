from __future__ import annotations

from types import SimpleNamespace

from app.modules.plans.domain.entities import PlanItem
from app.modules.plans.domain.entities import PreferredTimeWindow
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.place_selector.meal_selector import (
    MealStopSelector,
    _MealSlot,
    _TripMealOption,
)
from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.knowledge_graph.ontology import canonical_place_node_type
from app.modules.knowledge_graph.research.schema import SpecialtyMealCandidate


def test_meals_are_selected_after_activities_using_route_anchors() -> None:
    places = [
        _food("breakfast", "Breakfast restaurant", 21.03, 105.8005, "restaurant"),
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


def test_main_meal_policy_rejects_generic_food_and_dessert_venues() -> None:
    for name, place_type, tags in (
        ("Thu Hường Cake", "bakery", ["food", "breakfast"]),
        ("Chè Nhà Suvy", "dessert shop", ["food", "dessert"]),
        ("Chè Bốn Mùa", "food", ["food"]),
        ("The Note Coffee", "cafe", ["food", "coffee"]),
    ):
        assert not is_meal_place(
            tags=[place_type, *tags],
            source_activity=name,
        )


def test_main_meal_policy_accepts_restaurants_and_main_dish_venues() -> None:
    assert is_meal_place(
        tags=["restaurant", "food"],
        source_activity="Quán ăn Hà Nội",
    )
    assert is_meal_place(tags=["food"], source_activity="Bún chả Hương Liên")


def test_knowledge_graph_node_type_is_authoritative_for_meal_policy() -> None:
    assert is_meal_place(
        tags=["dessert"],
        source_activity="Provider category is noisy",
        ontology_type="Restaurant",
    )
    assert not is_meal_place(
        tags=["restaurant"],
        source_activity="Provider category is noisy",
        ontology_type="DrinkDessert",
    )


def test_url_provider_types_normalize_to_knowledge_graph_place_types() -> None:
    assert canonical_place_node_type("Vietnamese restaurant") == "Restaurant"
    assert canonical_place_node_type("Dessert shop") == "DrinkDessert"
    assert canonical_place_node_type("Coffee shop") == "DrinkDessert"
    assert canonical_place_node_type("Chè") == "DrinkDessert"
    assert canonical_place_node_type("food") == "TravelPlace"


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


def test_catalog_preferred_window_keeps_alcohol_venue_out_of_breakfast() -> None:
    evening = _food(
        "craft-beer",
        "Local Craft Beer Restaurant",
        21.03,
        105.801,
        "Restaurant",
    ).model_copy(
        update={
            "preferred_time_windows": [
                PreferredTimeWindow(start="18:00", end="21:00")
            ]
        }
    )
    places = [
        evening,
        _food("breakfast", "Breakfast restaurant", 21.03, 105.802, "Restaurant"),
        _food("lunch", "Lunch restaurant", 21.03, 105.803, "Restaurant"),
    ]

    selected = MealStopSelector(_PlaceTool(places)).select_for_trip(
        region_key="vn,ha-noi",
        activities_by_day={
            1: [
                _activity("activity-1", 21.03, 105.80),
                _activity("activity-2", 21.03, 105.82),
            ]
        },
        excluded_place_ids={"activity-1", "activity-2"},
    )

    assert selected[1]["breakfast_meal"].place_id != "craft-beer"
    assert selected[1]["dinner_meal"].place_id == "craft-beer"


def test_trip_meals_use_unique_dishes_before_a_necessary_repeat() -> None:
    places = [
        _food("bun-cha-one", "Bún chả Hương Liên", 21.03, 105.801, "Restaurant"),
        _food("bun-cha-two", "Bún chả Đắc Kim", 21.03, 105.802, "Restaurant"),
        _food("pho", "Phở Bát Đàn", 21.03, 105.803, "Restaurant"),
        _food("rice", "Cơm Hà Nội", 21.03, 105.804, "Restaurant"),
        _food("fallback", "Local restaurant", 21.03, 105.805, "Restaurant"),
    ]
    graph = _SpecialtyGraph()
    selector = MealStopSelector(_PlaceTool(places), graph_repository=graph)

    selected = selector.select_for_trip(
        region_key="vn,ha-noi",
        activities_by_day={
            1: [_activity("a1", 21.03, 105.80), _activity("a2", 21.03, 105.81)],
            2: [_activity("a3", 21.03, 105.81), _activity("a4", 21.03, 105.82)],
        },
        excluded_place_ids={"a1", "a2", "a3", "a4"},
    )

    chosen = [place for meals in selected.values() for place in meals.values() if place]
    assert graph.calls == 1
    assert len({place.place_id for place in chosen}) == len(chosen)
    # Six slots only have five unique venues. Every distinct meal key is used
    # before bún chả is allowed to repeat at the second source restaurant.
    assert sum("bún chả" in place.name.casefold() for place in chosen) == 2
    assert "pho" in {place.place_id for place in chosen}
    assert {"rice", "fallback"} <= {place.place_id for place in chosen}
    assert all(
        place is None or "bún chả" not in place.name.casefold()
        for meals in selected.values()
        for role, place in meals.items()
        if role != "lunch_meal"
    )


def test_trip_meals_penalize_repeated_specialty_but_allow_it_when_necessary() -> None:
    places = [
        _food("pho-one", "Phở Một", 21.03, 105.801, "Restaurant"),
        _food("pho-two", "Phở Hai", 21.03, 105.802, "Restaurant"),
    ]

    class _RepeatedSpecialtyGraph:
        def list_specialty_meal_candidates(self, region_key: str, *, limit: int):
            assert region_key == "vn,ha-noi"
            return [
                SpecialtyMealCandidate(
                    activityId=f"eat-{place_id}",
                    activityName="Ăn phở",
                    placeId=place_id,
                    itemId="food-pho",
                    itemName="Phở",
                    selectionPath="offers_item",
                )
                for place_id in ("pho-one", "pho-two")
            ]

    selected = MealStopSelector(
        _PlaceTool(places),
        graph_repository=_RepeatedSpecialtyGraph(),
    ).select_for_trip(
        region_key="vn,ha-noi",
        activities_by_day={
            1: [_activity("a1", 21.03, 105.80), _activity("a2", 21.03, 105.81)]
        },
        excluded_place_ids={"a1", "a2"},
    )

    chosen = [place for place in selected[1].values() if place is not None]
    assert {place.place_id for place in chosen} == {"pho-one", "pho-two"}
    assert all(place.source_activity == "Phở" for place in chosen)


def test_unused_generic_meal_beats_repeating_a_specialty() -> None:
    selector = MealStopSelector(_PlaceTool([]))
    slot = selector._rank_trip_options(
        [
            _TripMealOption(
                place=_food("pho-two", "Phở Hai", 21.03, 105.802, "Restaurant"),
                selection_path="offers_item",
                meal_key="phở",
                item_id="food-pho",
            ),
            _TripMealOption(
                place=_food("rice", "Cơm nhà", 21.03, 105.803, "Restaurant"),
                meal_key="cơm nhà",
            ),
        ],
        slot=_MealSlot(
            day=1,
            role="lunch_meal",
            first=_activity("a1", 21.03, 105.80),
            second=_activity("a2", 21.03, 105.81),
        ),
        region_key="vn,ha-noi",
        used_refs=set(),
        meal_key_usage={"phở": 1},
    )

    assert slot[0][1].place.place_id == "rice"


class _SpecialtyGraph:
    def __init__(self) -> None:
        self.calls = 0

    def list_specialty_meal_candidates(
        self, region_key: str, *, limit: int
    ) -> list[SpecialtyMealCandidate]:
        assert region_key == "vn,ha-noi"
        assert limit == 250
        self.calls += 1
        return [
            SpecialtyMealCandidate(
                activityId="bun-cha-huong-lien",
                activityName="Ăn bún chả Hương Liên",
                placeId="bun-cha-one",
                selectionPath="target_place",
                bestTimeSlots=["11:00-14:00"],
            ),
            SpecialtyMealCandidate(
                activityId="bun-cha-dac-kim",
                activityName="Ăn bún chả Đắc Kim ở Hàng Mành",
                placeId="bun-cha-two",
                selectionPath="target_place",
                bestTimeSlots=["11:00-14:00"],
            ),
            SpecialtyMealCandidate(
                activityId="pho",
                activityName="Ăn phở",
                placeId="pho",
                itemId="food-pho",
                itemName="Phở",
                selectionPath="offers_item",
                bestTimeSlots=["06:30-10:00", "11:00-14:00"],
            ),
        ]


def test_trip_meals_resolve_llm_selected_item_through_offers_item() -> None:
    places = [
        _food("pho-venue", "Phở gia truyền", 21.03, 105.801, "Restaurant"),
        _food("lunch", "Lunch restaurant", 21.03, 105.802, "Restaurant"),
        _food("dinner", "Dinner restaurant", 21.03, 105.803, "Restaurant"),
    ]

    class _Planner:
        def select_for_trip(self, **kwargs):
            assert list(kwargs["activities_by_day"]) == [1]
            return [
                SimpleNamespace(
                    day=1,
                    slot="breakfast",
                    node_id="food-pho",
                    node_name="Phở",
                )
            ]

    class _Graph:
        def list_specialty_meal_candidates(self, region_key: str, *, limit: int):
            return []

        def list_places_offering_items(self, item_ids: list[str], *, limit: int):
            assert item_ids == ["food-pho"]
            return [SimpleNamespace(id="pho-venue")]

    selected = MealStopSelector(
        _PlaceTool(places),
        graph_repository=_Graph(),
        meal_node_planner=_Planner(),
    ).select_for_trip(
        region_key="vn,ha-noi",
        activities_by_day={
            1: [_activity("a1", 21.03, 105.80), _activity("a2", 21.03, 105.81)]
        },
        excluded_place_ids={"a1", "a2"},
        interests=["local food"],
    )

    breakfast = selected[1]["breakfast_meal"]
    assert breakfast is not None
    assert breakfast.place_id == "pho-venue"
    assert breakfast.source_activity == "Phở"
    assert breakfast.selection_method == "meal_node_graph"
    assert "food-pho" in breakfast.candidate_entity_ids


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
