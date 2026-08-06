from __future__ import annotations

from app.modules.plans.domain.entities import (
    PlaceSelectionDay,
    PlaceSelectionBlueprint,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.dto.agent_contracts import (
    PlaceSelectionInput,
    PlanningIntent,
    TripPlanningSpec,
)
from app.modules.plans.place_selector.place_tool import SelectablePlace
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.place_selector import PlaceSelectorService
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer


def test_agent_finder_reads_budget_level_from_trip_spec() -> None:
    finder = PlaceSelectorService(FakeFinderPlaceTool({}, search_order=[]))
    selection_input = PlaceSelectionInput(
        intent=PlanningIntent(
            destination="Hà Nội",
            travelStyle="local",
            pace="balanced",
            interests=["culture"],
        ),
        tripSpec=TripPlanningSpec(
            days=1,
            budget={"level": "low"},
        ),
        regionKey="vn,ha-noi",
        tripThemes=_macro_plan().trip_themes,
        allowFinderGapFill=False,
    )

    result = finder.fill_agent_plan(selection_input)

    assert result.mode.value == "main"


def test_finder_uses_dynamic_skeleton_and_retries_candidates() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Selected museum",
            tags=["culture"],
            intensity="moderate",
            address="1 Selected Street, Ha Noi",
        ),
        "support": _place(
            "support",
            "Local restaurant",
            tags=["food"],
            intensity="light",
            address="2 Support Street, Ha Noi",
        ),
        "too-heavy": _place(
            "too-heavy",
            "Hard hike",
            tags=["nature"],
            intensity="high",
        ),
        "hotel-a": _place(
            "hotel-a",
            "Hotel A",
            tags=["accommodation"],
            intensity=None,
        ),
    }
    tool = FakeFinderPlaceTool(
        places,
        search_order=["too-heavy", "support"],
    )
    finder = PlaceSelectorService(tool, max_candidates_per_block=5)
    user_status = UserStatus.model_validate(
        {
            "activeAccommodationPlaceId": "hotel-a",
            "metrics": {
                "physical": 80,
                "mental": 80,
                "energy": 80,
            },
            "constraints": {"allowedActivityIntensities": ["light", "moderate"]},
        }
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Selected museum",
                mustVisit=True,
                tags=["culture"],
            )
        ],
        user_status=user_status,
    )

    day = result.days[0]
    selected_item = next(item for item in day.items if item.place_id == "selected-main")
    assert selected_item.source == "selected_place"
    assert selected_item.address == "1 Selected Street, Ha Noi"
    assert {item.role for item in day.items if item.timeline_category == "food"} == {
        "breakfast_meal",
        "lunch_meal",
        "dinner_meal",
    }
    assert result.final_plan_status.used_place_ids == ["selected-main"]
    assert result.final_plan_status.rejected_candidate_ids == ["too-heavy", "support"]
    assert result.final_plan_status.visited_tag_counts == {"culture": 1}
    assert result.final_user_status.metrics.physical == 70
    assert result.final_user_status.metrics.energy == 70
    assert result.final_user_status.location is not None
    assert result.final_user_status.location.place_id == "selected-main"
    assert result.unscheduled_places == []


def test_finder_preserves_address_from_selected_place_without_catalog_id() -> None:
    finder = PlaceSelectorService(FakeFinderPlaceTool({}, search_order=[]))
    macro_plan = _macro_plan().model_copy(
        update={
            "selection_days": [
                _macro_plan()
                .selection_days[0]
                .model_copy(
                    update={
                        "allocated_selected_place_refs": ["Hanoi Train Street (South)"]
                    }
                )
            ]
        }
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                name="Hanoi Train Street (South)",
                address="3 Trần Phú, Hoàn Kiếm, Hà Nội",
                latitude=21.0291,
                longitude=105.8425,
                mustVisit=True,
                tags=["culture"],
            )
        ],
        allow_finder_gap_fill=False,
    )

    selected_item = next(
        item for item in result.days[0].items if item.source == "selected_place"
    )
    assert selected_item.address == "3 Trần Phú, Hoàn Kiếm, Hà Nội"


def test_finder_resolves_local_meal_slots_without_using_accommodation() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Văn Miếu",
            tags=["culture"],
            intensity="light",
        ),
        "hotel": _place(
            "hotel",
            "Conifer Hotel",
            tags=["accommodation", "hotel"],
            intensity=None,
            place_type="hotel",
        ),
        "local-lunch": _place(
            "local-lunch",
            "Bún chả Hà Nội",
            tags=["food", "local", "hanoi_cuisine"],
            intensity=None,
            place_type="restaurant",
        ),
        "gallery": _place(
            "gallery",
            "Nhà triển lãm Mỹ thuật",
            tags=["culture", "gallery"],
            intensity="light",
        ),
        "local-dinner": _place(
            "local-dinner",
            "Chả cá Hà Nội",
            tags=["food", "local", "hanoi_cuisine"],
            intensity=None,
            place_type="restaurant",
        ),
    }
    tool = FakeFinderPlaceTool(
        places,
        search_order=[
            "hotel",
            "local-lunch",
            "gallery",
            "local-dinner",
        ],
    )
    finder = PlaceSelectorService(tool)

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Văn Miếu",
                mustVisit=True,
                tags=["culture"],
            )
        ],
    )

    day = result.days[0]
    resolved_meals = {
        item.place_id
        for item in day.items
        if item.timeline_category == "food" and item.place_id is not None
    }
    assert resolved_meals <= {"local-lunch", "local-dinner"}
    assert resolved_meals
    assert any(item.place_id == "gallery" for item in day.items)
    assert all(item.place_id != "hotel" for item in day.items)
    assert all(
        item.notes != "Selected by deterministic Finder candidate loop."
        for item in day.items
    )
    assert not any(
        "unresolved meal placeholder" in warning for warning in result.warnings
    )


def test_finder_uses_proximity_to_break_relevance_ties() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Văn Miếu",
            tags=["culture"],
            intensity="light",
            latitude=21.0300,
            longitude=105.8500,
        ),
        "far-culture": _place(
            "far-culture",
            "Điểm văn hóa xa",
            tags=["culture"],
            intensity="light",
            latitude=21.1200,
            longitude=105.9500,
        ),
        "near-culture": _place(
            "near-culture",
            "Điểm văn hóa gần",
            tags=["culture"],
            intensity="light",
            latitude=21.0310,
            longitude=105.8510,
        ),
    }
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            places,
            search_order=["far-culture", "near-culture"],
        )
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Văn Miếu",
                mustVisit=True,
                tags=["culture"],
            )
        ],
    )

    support = next(
        item for item in result.days[0].items if item.source == "finder_suggestion"
    )
    assert support.place_id == "near-culture"


def test_finder_keeps_relevance_ahead_of_proximity() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Văn Miếu",
            tags=["culture"],
            intensity="light",
            latitude=21.0300,
            longitude=105.8500,
        ),
        "far-relevant": _place(
            "far-relevant",
            "Không gian văn hóa phù hợp",
            tags=["culture"],
            intensity="light",
            latitude=21.0350,
            longitude=105.8550,
        ),
        "near-generic": _place(
            "near-generic",
            "Điểm tham quan chung",
            tags=[],
            intensity="light",
            latitude=21.0301,
            longitude=105.8501,
        ),
        "mid-relevant": _place(
            "mid-relevant",
            "Bảo tàng văn hóa phù hợp",
            tags=["culture"],
            intensity="light",
            latitude=21.0330,
            longitude=105.8530,
        ),
    }
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            places,
            search_order=["far-relevant", "near-generic", "mid-relevant"],
        )
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Văn Miếu",
                mustVisit=True,
                tags=["culture"],
            )
        ],
    )

    suggestion_ids = {
        item.place_id
        for item in result.days[0].items
        if item.source == "finder_suggestion"
    }
    assert suggestion_ids == {"far-relevant", "mid-relevant"}
    assert "near-generic" not in suggestion_ids


def test_reference_only_mode_never_adds_catalog_places() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Place from OCR",
            tags=["culture"],
            intensity="light",
        ),
        "catalog-support": _place(
            "catalog-support",
            "Planner catalog suggestion",
            tags=["food"],
            intensity="light",
        ),
    }
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            places,
            search_order=["catalog-support"],
        )
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Place from OCR",
                sourceRefs=["ocr"],
                tags=["culture"],
            )
        ],
        allow_finder_gap_fill=False,
    )

    activity_items = [
        item
        for item in result.days[0].items
        if item.source in {"selected_place", "finder_suggestion"}
    ]
    assert [item.name for item in activity_items] == ["Place from OCR"]
    assert all(item.source != "finder_suggestion" for item in activity_items)


def test_reference_only_mode_leaves_unallocated_days_empty() -> None:
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            {
                "catalog-support": _place(
                    "catalog-support",
                    "Planner catalog suggestion",
                    tags=["food"],
                    intensity="light",
                )
            },
            search_order=["catalog-support"],
        )
    )
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Reference only",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["food"],
            )
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [],
        allow_finder_gap_fill=False,
    )

    assert result.days[0].strategy == "reference_only"
    assert len(result.days[0].items) == 3
    assert all(item.timeline_category == "food" for item in result.days[0].items)
    assert all(item.source == "finder_rule" for item in result.days[0].items)


def test_reference_intake_adds_catalog_only_to_empty_requested_days() -> None:
    source = _place(
        "source-place",
        "Place from video",
        tags=["culture"],
        intensity="light",
    )
    catalog = _place(
        "catalog-place",
        "Finder suggestion",
        tags=["food"],
        intensity="light",
        place_type="restaurant",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            {
                "source-place": source,
                "catalog-place": catalog,
            },
            search_order=["catalog-place"],
        )
    )
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="From video",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture"],
                allocatedSelectedPlaceRefs=["source-place"],
            ),
            PlaceSelectionDay(
                day=2,
                theme="Finder fill",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                focusTags=["food"],
            ),
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId="source-place",
                name="Place from video",
                sourceRefs=["https://example.com/reel"],
                sourceProvider="google_maps_scraper",
                sourceOrder=1,
                tags=["culture"],
            )
        ],
        allow_finder_gap_fill=True,
    )

    source_item = next(
        item for item in result.days[0].items if item.name == "Place from video"
    )
    assert source_item.source_provider == "google_maps_scraper"
    assert any(item.source == "finder_suggestion" for item in result.days[0].items)
    assert {item.role for item in result.days[1].items} >= {
        "breakfast_meal",
        "lunch_meal",
        "dinner_meal",
    }


def test_route_first_supplements_reference_days_with_catalog_places() -> None:
    source = _place(
        "source-place",
        "Place from video",
        tags=["culture"],
        intensity="light",
    )
    catalog_places = {
        "catalog-museum": _place(
            "catalog-museum",
            "Nearby museum",
            tags=["culture"],
            intensity="light",
        ),
        "catalog-lake": _place(
            "catalog-lake",
            "Nearby lake",
            tags=["nature"],
            intensity="light",
        ),
        "catalog-food": _place(
            "catalog-food",
            "Nearby lunch restaurant",
            tags=["food"],
            intensity="light",
            place_type="restaurant",
            latitude=21.031,
            longitude=105.851,
        ),
        "catalog-dinner": _place(
            "catalog-dinner",
            "Nearby dinner restaurant",
            tags=["food"],
            intensity="light",
            place_type="restaurant",
            latitude=21.032,
            longitude=105.852,
        ),
        "catalog-breakfast": _place(
            "catalog-breakfast",
            "Nearby breakfast bakery",
            tags=["food", "bakery", "breakfast"],
            intensity="light",
            place_type="bakery",
            latitude=21.029,
            longitude=105.849,
        ),
    }
    tool = FakeFinderPlaceTool(
        {source.place_id: source, **catalog_places},
        search_order=list(catalog_places),
    )
    finder = PlaceSelectorService(
        tool,
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )
    macro_plan = PlaceSelectionBlueprint(
        title="Hanoi",
        destination="Hanoi",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Culture",
                targetArea="Hanoi",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=[source.place_id],
            )
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId=source.place_id,
                name=source.name,
                sourceRefs=["https://example.com/reel"],
                tags=["culture"],
            )
        ],
        allow_finder_gap_fill=True,
    )

    real_items = [item for item in result.days[0].items if item.place_id]
    assert len(real_items) == 6
    assert sum(item.timeline_category == "activity" for item in real_items) == 3
    assert sum(item.timeline_category == "food" for item in real_items) == 3
    assert any(item.name == source.name for item in real_items)
    assert any(item.source == "finder_suggestion" for item in real_items)
    assert not any(
        item.place_type == "meal" and item.source == "finder_rule"
        for item in result.days[0].items
    )
    assert not any(
        item.role == "group_social_activity" for item in result.days[0].items
    )


def test_route_first_keeps_generic_meal_anchors_when_no_venue_resolves() -> None:
    source = _place(
        "source-place",
        "Place from video",
        tags=["culture"],
        intensity="light",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool({source.place_id: source}, search_order=[]),
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )
    macro_plan = _macro_plan().model_copy(
        update={
            "selection_days": [
                _macro_plan()
                .selection_days[0]
                .model_copy(update={"allocated_selected_place_refs": [source.place_id]})
            ]
        }
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId=source.place_id,
                name=source.name,
                sourceRefs=["https://example.com/reel"],
                tags=["culture"],
            )
        ],
        allow_finder_gap_fill=False,
    )

    assert [item.role for item in result.days[0].items] == [
        "breakfast_meal",
        "main_activity_1",
        "lunch_meal",
        "dinner_meal",
    ]
    generic_meals = [
        item for item in result.days[0].items if item.source == "finder_rule"
    ]
    assert [item.name for item in generic_meals] == ["Ăn sáng", "Ăn trưa", "Ăn tối"]
    assert (
        sum("uses a generic meal anchor" in warning for warning in result.warnings) == 3
    )


def test_route_first_url_food_replaces_finder_meal_and_cafe_stays_activity() -> None:
    source_cafe = _place(
        "source-cafe",
        "Cafe Đinh",
        tags=["cafe", "coffee"],
        intensity="light",
        place_type="cafe",
    )
    source_lunch = _place(
        "source-lunch",
        "Bún đậu Tuấn Trọc",
        tags=["food"],
        intensity=None,
        place_type="restaurant",
    )
    catalog_places = {
        "catalog-cafe": _place(
            "catalog-cafe",
            "Cafe Finder không được thêm",
            tags=["cafe", "coffee"],
            intensity="light",
            place_type="cafe",
        ),
        "catalog-museum": _place(
            "catalog-museum",
            "Bảo tàng Phụ nữ Việt Nam",
            tags=["culture"],
            intensity="light",
        ),
        "catalog-breakfast": _place(
            "catalog-breakfast",
            "Tiệm bánh buổi sáng",
            tags=["food", "breakfast"],
            intensity=None,
            place_type="bakery",
        ),
        "catalog-lunch": _place(
            "catalog-lunch",
            "Nhà hàng trưa Finder",
            tags=["food", "lunch"],
            intensity=None,
            place_type="restaurant",
        ),
        "catalog-dinner": _place(
            "catalog-dinner",
            "Nhà hàng tối Finder",
            tags=["food", "dinner"],
            intensity=None,
            place_type="restaurant",
        ),
    }
    tool = FakeFinderPlaceTool(
        {
            source_cafe.place_id: source_cafe,
            source_lunch.place_id: source_lunch,
            **catalog_places,
        },
        search_order=list(catalog_places),
    )
    finder = PlaceSelectorService(
        tool,
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )
    macro_plan = _macro_plan().model_copy(
        update={
            "selection_days": [
                _macro_plan()
                .selection_days[0]
                .model_copy(
                    update={
                        "allocated_selected_place_refs": [
                            source_cafe.place_id,
                            source_lunch.place_id,
                        ]
                    }
                )
            ]
        }
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId=source_cafe.place_id,
                name=source_cafe.name,
                sourceRefs=["https://example.com/reel"],
                sourceOrder=1,
                tags=["cafe", "coffee"],
            ),
            SelectedPlaceContext(
                placeId=source_lunch.place_id,
                name=source_lunch.name,
                sourceRefs=["https://example.com/reel"],
                sourceOrder=2,
                sourceTimeHint="lunch",
                tags=["food"],
            ),
        ],
        allow_finder_gap_fill=True,
    )

    day_items = {item.role: item for item in result.days[0].items}
    assert day_items["main_activity_1"].place_id == "source-cafe"
    assert day_items["main_activity_1"].timeline_category == "activity"
    assert day_items["lunch_meal"].place_id == "source-lunch"
    assert day_items["lunch_meal"].source == "selected_place"
    assert all(item.place_id != "catalog-lunch" for item in result.days[0].items)
    assert all(item.place_id != "catalog-cafe" for item in result.days[0].items)
    assert result.unscheduled_places == []


def test_finder_adds_at_most_one_coffee_stop_per_day() -> None:
    catalog = {
        "cafe-one": _place(
            "cafe-one",
            "Coffee One",
            tags=["cafe", "coffee"],
            intensity="light",
            place_type="cafe",
        ),
        "cafe-two": _place(
            "cafe-two",
            "Coffee Two",
            tags=["cafe", "coffee"],
            intensity="light",
            place_type="cafe",
        ),
        "museum": _place(
            "museum",
            "Local Museum",
            tags=["culture"],
            intensity="light",
            place_type="museum",
        ),
        "gallery": _place(
            "gallery",
            "Local Gallery",
            tags=["culture"],
            intensity="light",
            place_type="museum",
        ),
    }
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(catalog, search_order=list(catalog)),
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )
    macro_plan = _macro_plan().model_copy(deep=True)
    macro_plan.selection_days[0].theme = "Coffee and culture"
    macro_plan.selection_days[0].focus_tags = ["coffee", "culture"]
    macro_plan.selection_days[0].allocated_selected_place_refs = []

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [],
        allow_finder_gap_fill=True,
    )

    coffee_items = [
        item
        for item in result.days[0].items
        if item.place_id in {"cafe-one", "cafe-two"}
    ]
    assert len(coffee_items) == 1
    non_food_non_coffee = [
        item
        for item in result.days[0].items
        if item.timeline_category == "activity"
        and item.place_id in {"museum", "gallery"}
    ]
    assert len(non_food_non_coffee) == 2


def test_route_first_url_food_only_fills_daytime_activity_gaps() -> None:
    source_meals = [
        _place(
            f"source-meal-{index}",
            name,
            tags=["food", role],
            intensity=None,
            place_type="restaurant",
        )
        for index, (name, role) in enumerate(
            [
                ("Phở sáng từ URL", "breakfast"),
                ("Bún chả trưa từ URL", "lunch"),
                ("Cơm tối từ URL", "dinner"),
            ],
            start=1,
        )
    ]
    finder_activities = {
        "finder-morning": _place(
            "finder-morning",
            "Bảo tàng buổi sáng",
            tags=["culture"],
            intensity="light",
            latitude=21.025,
            longitude=105.845,
        ),
        "finder-afternoon": _place(
            "finder-afternoon",
            "Công viên buổi chiều",
            tags=["culture"],
            intensity="light",
            latitude=21.035,
            longitude=105.855,
        ),
    }
    tool = FakeFinderPlaceTool(
        {
            **{place.place_id: place for place in source_meals},
            **finder_activities,
        },
        search_order=list(finder_activities),
    )
    finder = PlaceSelectorService(
        tool,
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )
    selected = [
        SelectedPlaceContext(
            placeId=place.place_id,
            name=place.name,
            sourceRefs=["https://example.com/food-reel"],
            sourceOrder=index,
            sourceTimeHint=role,
            tags=place.tags,
        )
        for index, (place, role) in enumerate(
            zip(source_meals, ("breakfast", "lunch", "dinner"), strict=True),
            start=1,
        )
    ]
    macro_plan = _macro_plan().model_copy(
        update={
            "selection_days": [
                _macro_plan()
                .selection_days[0]
                .model_copy(
                    update={
                        "allocated_selected_place_refs": [
                            place.stable_ref for place in selected
                        ]
                    }
                )
            ]
        }
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        selected,
        allow_finder_gap_fill=True,
        allow_replace_source_places=False,
    )

    items = result.days[0].items
    assert [
        item.role for item in items if item.timeline_category == "food"
    ] == [
        "breakfast_meal",
        "lunch_meal",
        "dinner_meal",
    ]
    assert sum(item.timeline_category == "activity" for item in items) == 2
    assert {item.place_id for item in items if item.timeline_category == "food"} == {
        place.place_id for place in source_meals
    }
    assert all(
        item.source == "finder_suggestion"
        for item in items
        if item.timeline_category == "activity"
    )
    assert result.unscheduled_places == []


def test_route_first_keeps_every_url_stop_across_activity_and_meal_slots() -> None:
    selected = [
        SelectedPlaceContext(
            name=name,
            sourceRefs=["https://example.com/hanoi-video"],
            sourceOrder=order,
            sourceDay=day,
            sourceTimeHint=time_hint,
            tags=tags,
            latitude=21.02 + order / 1000,
            longitude=105.84 + order / 1000,
        )
        for order, (name, day, time_hint, tags) in enumerate(
            [
                ("Ho Chi Minh's Mausoleum", 1, "morning", ["other"]),
                ("Nhà thờ Lớn Hà Nội", 1, "afternoon", ["food"]),
                ("Hanoi Train Street (South)", 2, "afternoon", ["cafe"]),
                ("Bún đậu Tuấn Trọc", 2, "lunch", ["food"]),
                ("Hồ Hoàn Kiếm", 3, "afternoon", ["food", "outdoor"]),
                ("Xôi chè bà Thìn", 3, "dinner", ["food"]),
            ],
            start=1,
        )
    ]
    allocated_by_day = {
        1: [selected[0].stable_ref, selected[1].stable_ref],
        2: [selected[2].stable_ref, selected[3].stable_ref],
        3: [selected[4].stable_ref, selected[5].stable_ref],
    }
    macro_plan = PlaceSelectionBlueprint(
        title="Hanoi from URL",
        destination="Hanoi",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=day,
                theme=f"URL day {day}",
                targetArea="Hanoi",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=allocated_by_day[day],
            )
            for day in range(1, 4)
        ],
    )
    finder = PlaceSelectorService(
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer())
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        selected,
        allow_finder_gap_fill=True,
    )

    scheduled_url_names = {
        item.name
        for day in result.days
        for item in day.items
        if item.source == "selected_place"
    }
    assert scheduled_url_names == {place.name for place in selected}
    assert result.unscheduled_places == []


def test_finder_deduplicates_catalog_alias_against_url_place() -> None:
    source = _place(
        "source-train-street",
        "Phố đường tàu",
        tags=["culture"],
        intensity="light",
        latitude=21.0291,
        longitude=105.8412,
    )
    duplicate = _place(
        "catalog-train-street",
        "Phố đường tàu Hà Nội",
        tags=["culture"],
        intensity="light",
        latitude=21.0292,
        longitude=105.8413,
    )
    unique = _place(
        "catalog-museum",
        "Bảo tàng Phụ nữ Việt Nam",
        tags=["culture"],
        intensity="light",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            {
                source.place_id: source,
                duplicate.place_id: duplicate,
                unique.place_id: unique,
            },
            search_order=[duplicate.place_id, unique.place_id],
        )
    )
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Stops from URL",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                allocatedSelectedPlaceRefs=[source.place_id],
            ),
            PlaceSelectionDay(
                day=2,
                theme="Finder fill",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture"],
            ),
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId=source.place_id,
                name=source.name,
                sourceRefs=["https://example.com/reel"],
                sourceOrder=1,
                tags=["culture"],
                latitude=source.latitude,
                longitude=source.longitude,
            )
        ],
        allow_finder_gap_fill=True,
    )

    names = [item.name for day in result.days for item in day.items]
    assert "Phố đường tàu" in names
    assert "Phố đường tàu Hà Nội" not in names
    assert "Bảo tàng Phụ nữ Việt Nam" in names


def test_finder_caps_only_its_own_suggestions_per_empty_day() -> None:
    names = [
        "Museum",
        "Temple",
        "Lake",
        "Garden",
        "Theatre",
        "Gallery",
        "Citadel",
    ]
    places = {
        f"catalog-{index}": _place(
            f"catalog-{index}",
            name,
            tags=["culture"],
            intensity="light",
        )
        for index, name in enumerate(names, start=1)
    }
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            places,
            search_order=list(places),
        )
    )
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Finder-only day",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture"],
                pace="packed",
            )
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent().model_copy(update={"pace": TravelPace.packed}),
        [],
        allow_finder_gap_fill=True,
    )

    suggestions = [
        item for item in result.days[0].items if item.source == "finder_suggestion"
    ]
    assert len(suggestions) == 3


def test_low_user_capacity_switches_day_to_relaxed_skeleton() -> None:
    finder = PlaceSelectorService(FakeFinderPlaceTool({}, search_order=[]))
    user_status = UserStatus.model_validate(
        {
            "metrics": {
                "physical": 35,
                "energy": 50,
            }
        }
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [],
        user_status=user_status,
    )

    assert result.days[0].strategy == "meal_anchored_timeline"
    assert [item.role for item in result.days[0].items] == [
        "breakfast_meal",
        "lunch_meal",
        "dinner_meal",
    ]


def test_finder_reports_selected_place_that_cannot_be_allocated() -> None:
    heavy = _place(
        "selected-heavy",
        "Hard hike",
        tags=["nature"],
        intensity="high",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool({"selected-heavy": heavy}, search_order=[]),
    )
    user_status = UserStatus.model_validate(
        {"constraints": {"allowedActivityIntensities": ["light"]}}
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-heavy",
                name="Hard hike",
                mustVisit=True,
            )
        ],
        user_status=user_status,
    )

    assert result.final_plan_status.used_place_ids == []
    assert result.unscheduled_places[0].place_id == "selected-heavy"
    assert result.unscheduled_places[0].reason_code == "insufficient_time"


def test_catalog_cannot_consume_a_selected_place_before_its_allocated_day() -> None:
    selected = _place(
        "selected-day-2",
        "Selected day two",
        tags=["culture"],
        intensity="light",
    )
    support = _place(
        "support",
        "Catalog support",
        tags=["food"],
        intensity="light",
    )
    tool = FakeFinderPlaceTool(
        {"selected-day-2": selected, "support": support},
        search_order=["selected-day-2", "support"],
    )
    finder = PlaceSelectorService(tool)
    macro_plan = PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Food",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["food"],
            ),
            PlaceSelectionDay(
                day=2,
                theme="Culture",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture"],
                allocatedSelectedPlaceRefs=["selected-day-2"],
            ),
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-day-2",
                name="Selected day two",
                mustVisit=True,
                tags=["culture"],
            )
        ],
    )

    assert all(item.place_id != "selected-day-2" for item in result.days[0].items)
    assert any(item.place_id == "selected-day-2" for item in result.days[1].items)


def test_finder_rejects_place_outside_opening_hours() -> None:
    closed_morning = _place(
        "closed-morning",
        "Late museum",
        tags=["culture"],
        intensity="light",
        opening_hours=[{"openTime": "14:00", "closeTime": "22:00"}],
    )
    backup = _place(
        "backup",
        "Morning museum",
        tags=["culture"],
        intensity="light",
        opening_hours=[{"openTime": "08:00", "closeTime": "18:00"}],
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            {"closed-morning": closed_morning, "backup": backup},
            search_order=["closed-morning", "backup"],
        )
    )

    result = finder.fill_main_plan(_macro_plan(), _intent(), [])

    assert any(item.name == "Morning museum" for item in result.days[0].items)
    assert "closed-morning" in result.final_plan_status.rejected_candidate_ids


def test_bad_weather_uses_indoor_skeleton_and_rejects_outdoor_places() -> None:
    outdoor = _place(
        "outdoor",
        "Outdoor walk",
        tags=["outdoor", "nature"],
        intensity="light",
        weather_sensitivity="high",
    )
    indoor = _place(
        "indoor",
        "Indoor gallery",
        tags=["culture", "indoor"],
        intensity="light",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            {"outdoor": outdoor, "indoor": indoor},
            search_order=["outdoor", "indoor"],
        )
    )
    intent = _intent().model_copy(update={"constraints": ["bad_weather"]})

    result = finder.fill_main_plan(_macro_plan(), intent, [])

    assert result.days[0].strategy == "meal_anchored_timeline"
    assert any(item.name == "Indoor gallery" for item in result.days[0].items)
    assert "outdoor" in result.final_plan_status.rejected_candidate_ids


def test_constraint_policy_rejects_cemetery_and_keeps_coastal_place() -> None:
    cemetery = _place(
        "cemetery",
        "Nghĩa trang liệt sĩ Hải Phòng",
        tags=["cemetery", "culture"],
        intensity="light",
        place_type="grave_yard",
    )
    coastal = _place(
        "coastal",
        "Điểm ngắm biển Đồ Sơn",
        tags=["coastal", "culture"],
        intensity="light",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool(
            {"cemetery": cemetery, "coastal": coastal},
            search_order=["cemetery", "coastal"],
        )
    )
    intent = _intent().model_copy(
        update={
            "constraint_policy": ConstraintPolicy(
                excludedPlaceTypes=["cemetery"],
                geographicScope={"type": "coastal"},
            )
        }
    )

    result = finder.fill_main_plan(_macro_plan(), intent, [])

    assert any(item.place_id == "coastal" for item in result.days[0].items)
    assert "cemetery" in result.final_plan_status.rejected_candidate_ids


def test_constraint_policy_reports_inland_selected_place_as_unscheduled() -> None:
    inland = _place(
        "inland",
        "Bảo tàng nội đô",
        tags=["culture"],
        intensity="light",
    )
    finder = PlaceSelectorService(
        FakeFinderPlaceTool({"inland": inland}, search_order=[]),
    )
    intent = _intent().model_copy(
        update={
            "constraint_policy": ConstraintPolicy(
                geographicScope={"type": "coastal"},
            )
        }
    )
    macro = _macro_plan().model_copy(
        update={
            "selection_days": [
                _macro_plan()
                .selection_days[0]
                .model_copy(update={"allocated_selected_place_refs": ["inland"]})
            ]
        }
    )

    result = finder.fill_main_plan(
        macro,
        intent,
        [
            SelectedPlaceContext(
                placeId="inland",
                name="Bảo tàng nội đô",
                mustVisit=True,
                tags=["culture"],
            )
        ],
    )

    assert result.unscheduled_places[0].reason_code == "outside_geographic_scope"


class FakeFinderPlaceTool:
    def __init__(
        self,
        places: dict[str, SelectablePlace],
        *,
        search_order: list[str],
    ) -> None:
        self.places = places
        self.search_order = search_order
        self.search_queries: list[list[str]] = []

    def get(self, place_id: str) -> SelectablePlace | None:
        return self.places.get(place_id)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[SelectablePlace]:
        self.search_queries.append(list(target_tags))
        return [
            self.places[place_id]
            for place_id in self.search_order
            if place_id not in excluded_place_ids
        ][:limit]


def _macro_plan() -> PlaceSelectionBlueprint:
    return PlaceSelectionBlueprint(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        selectionDays=[
            PlaceSelectionDay(
                day=1,
                theme="Culture and food",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["culture", "food"],
                allocatedSelectedPlaceRefs=["selected-main"],
            )
        ],
    )


def _intent() -> TravelIntent:
    return TravelIntent(
        destination="Hà Nội",
        days=1,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["culture", "food"],
    )


def _place(
    place_id: str,
    name: str,
    *,
    tags: list[str],
    intensity: str | None,
    duration: int = 60,
    opening_hours: list[dict] | None = None,
    weather_sensitivity: str | None = None,
    price_level: str | None = None,
    place_type: str = "attraction",
    latitude: float = 21.03,
    longitude: float = 105.85,
    address: str | None = None,
) -> SelectablePlace:
    return SelectablePlace(
        placeId=place_id,
        name=name,
        address=address,
        placeType=place_type,
        regionKey="vn,ha-noi,hoan-kiem",
        tags=tags,
        latitude=latitude,
        longitude=longitude,
        typicalDurationMinutes=duration,
        activityIntensity=intensity,
        openingHours=opening_hours or [],
        weatherSensitivity=weather_sensitivity,
        priceLevel=price_level,
        dataConfidence="high",
    )


def test_finder_leaves_route_aware_midnight_overflow_unscheduled() -> None:
    macro = _macro_plan().model_copy(
        update={
            "selection_days": [
                _macro_plan()
                .selection_days[0]
                .model_copy(
                    update={"allocated_selected_place_refs": ["late-1", "late-2"]}
                )
            ]
        }
    )
    result = PlaceSelectorService().fill_main_plan(
        macro,
        _intent(),
        [
            SelectedPlaceContext(
                placeId="late-1",
                name="Late place 1",
                sourceRefs=["https://example.com/reel"],
                sourceOrder=1,
                sourceTimeHint="night",
                sourceDurationMinutes=180,
            ),
            SelectedPlaceContext(
                placeId="late-2",
                name="Late place 2",
                sourceRefs=["https://example.com/reel"],
                sourceOrder=2,
                sourceDurationMinutes=60,
            ),
        ],
        allow_finder_gap_fill=False,
    )

    represented = {item.name for item in result.days[0].items} | {
        item.name for item in result.unscheduled_places
    }
    assert {"Late place 1", "Late place 2"} <= represented
    assert {item.role for item in result.days[0].items} >= {
        "breakfast_meal",
        "lunch_meal",
        "dinner_meal",
    }
    assert all(
        int(item.time_window[:2]) < 24
        and int(item.time_window.split("-", 1)[1][:2]) < 24
        for item in result.days[0].items
    )
