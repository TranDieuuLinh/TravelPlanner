from __future__ import annotations

from app.modules.plans.domain.entities import (
    DayBrief,
    MacroPlan,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.domain.constraint_policy import ConstraintPolicy
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    FinderAgentInput,
    PlanningIntent,
    TripPlanningSpec,
)
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.finder.place_tool import FinderPlace


def test_agent_finder_reads_budget_level_from_trip_spec() -> None:
    finder = FinderService(FakeFinderPlaceTool({}, search_order=[]))
    finder_input = FinderAgentInput(
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
        macroPlan=AgentMacroPlan.model_validate(
            _macro_plan().model_dump(by_alias=True)
        ),
        allowFinderSuggestions=False,
    )

    result = finder.fill_agent_plan(finder_input)

    assert result.mode.value == "main"


def test_agent_finder_keeps_suggestions_inside_verified_tourism_zone() -> None:
    places = {
        "far-museum": _place(
            "far-museum",
            "Far museum",
            tags=["culture", "museum"],
            intensity="light",
            latitude=21.1200,
            longitude=105.9300,
        ),
        "local-museum": _place(
            "local-museum",
            "Local museum",
            tags=["culture", "museum"],
            intensity="light",
            latitude=21.0307,
            longitude=105.8372,
        ),
        "local-food": _place(
            "local-food",
            "Local lunch",
            tags=["food"],
            intensity="light",
            place_type="restaurant",
            latitude=21.0310,
            longitude=105.8380,
        ),
    }
    finder = FinderService(
        FakeFinderPlaceTool(
            places,
            search_order=["far-museum", "local-museum", "local-food"],
        )
    )
    macro = AgentMacroPlan.model_validate(
        _macro_plan().model_dump(by_alias=True)
    )
    macro.day_briefs[0] = macro.day_briefs[0].model_copy(
        update={
            "allocated_selected_place_refs": [],
            "tourism_zone_ref": "ba-dinh-museum-zone",
            "primary_activity_category": "attraction",
        }
    )
    finder_input = FinderAgentInput(
        intent=PlanningIntent(
            destination="Hà Nội",
            travelStyle="local",
            pace="balanced",
            interests=["culture"],
        ),
        tripSpec=TripPlanningSpec(days=1),
        macroPlan=macro,
        tourismZones=[
            {
                "zoneId": "ba-dinh-museum-zone",
                "regionKey": "vn,ha-noi,ba-dinh",
                "centerLatitude": 21.0306,
                "centerLongitude": 105.8370,
                "radiusMeters": 2500,
                "capabilities": ["culture", "food"],
                "primaryCategories": ["attraction", "food_drink"],
                "categoryCoverage": {"attraction": 1, "food_drink": 1},
                "anchorPlaces": [],
                "placeCount": 2,
                "compactnessScore": 0.9,
                "popularityScore": 0.9,
            }
        ],
    )

    result = finder.fill_agent_plan(finder_input)
    names = [item.name for item in result.final_days[0].items]

    assert "Local museum" in names
    assert "Far museum" not in names


def test_agent_finder_allows_famous_verified_place_beyond_core_zone() -> None:
    famous = _place(
        "famous-museum",
        "Famous Hanoi Museum",
        tags=["culture", "museum"],
        intensity="light",
        latitude=21.0800,
        longitude=105.8370,
    ).model_copy(
        update={
            "rating": 4.7,
            "review_count": 8_000,
            "data_confidence": "high",
        }
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {"famous-museum": famous},
            search_order=["famous-museum"],
        )
    )
    macro = AgentMacroPlan.model_validate(
        _macro_plan().model_dump(by_alias=True)
    )
    macro.day_briefs[0] = macro.day_briefs[0].model_copy(
        update={
            "allocated_selected_place_refs": [],
            "tourism_zone_ref": "museum-zone",
            "primary_activity_category": "attraction",
        }
    )

    finder_input = FinderAgentInput(
        intent=PlanningIntent(
            destination="Hà Nội",
            travelStyle="local",
            pace="balanced",
            interests=["culture"],
        ),
        tripSpec=TripPlanningSpec(days=1),
        macroPlan=macro,
        tourismZones=[
            {
                "zoneId": "museum-zone",
                "regionKey": "vn,ha-noi,ba-dinh",
                "centerLatitude": 21.0306,
                "centerLongitude": 105.8370,
                "radiusMeters": 2500,
                "capabilities": ["culture"],
                "primaryCategories": ["attraction"],
                "categoryCoverage": {"attraction": 1},
                "anchorPlaces": [],
                "placeCount": 1,
                "compactnessScore": 0.8,
                "popularityScore": 0.9,
            }
        ],
    )
    result = finder.fill_agent_plan(finder_input)

    assert any(
        item.place_id == "famous-museum"
        for item in result.final_days[0].items
    )

    locked_macro = finder_input.macro_plan.model_copy(deep=True)
    locked_macro.day_briefs[0] = locked_macro.day_briefs[0].model_copy(
        update={"main_region_locked": True}
    )
    locked_result = finder.fill_agent_plan(
        finder_input.model_copy(update={"macro_plan": locked_macro})
    )

    assert all(
        item.place_id != "famous-museum"
        for item in locked_result.final_days[0].items
    )


def test_finder_uses_fixed_skeleton_and_retries_candidates() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Selected museum",
            tags=["culture"],
            intensity="moderate",
        ),
        "support": _place(
            "support",
            "Local cultural center",
            tags=["culture"],
            intensity="light",
            place_type="cultural center",
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
    finder = FinderService(tool, max_candidates_per_block=5)
    user_status = UserStatus.model_validate(
        {
            "activeAccommodationPlaceId": "hotel-a",
            "metrics": {
                "physical": 80,
                "mental": 80,
                "energy": 80,
            },
            "constraints": {
                "allowedActivityIntensities": ["light", "moderate"]
            },
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
    assert [item.role for item in day.items] == [
        "breakfast_meal",
        "main_activity",
        "lunch_meal",
        "support_activity",
        "dinner_meal",
    ]
    assert day.items[1].source == "selected_place"
    assert day.items[3].source == "finder_suggestion"
    assert result.final_plan_status.used_place_ids == [
        "selected-main",
        "support",
    ]
    assert result.final_plan_status.rejected_candidate_ids == ["too-heavy"]
    assert result.final_plan_status.visited_tag_counts == {
        "culture": 2,
    }
    assert result.final_user_status.metrics.physical == 65
    assert result.final_user_status.metrics.energy == 80
    assert result.final_user_status.location is not None
    assert result.final_user_status.location.place_id == "hotel-a"
    assert result.unscheduled_places == []


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
        "coffee-only": _place(
            "coffee-only",
            "Cafe Dinh",
            tags=["food", "coffee"],
            intensity=None,
            place_type="coffee_shop",
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
            "gallery",
            "coffee-only",
            "local-lunch",
            "local-dinner",
        ],
    )
    finder = FinderService(tool)

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
    scheduled_by_role = {
        item.role: item
        for item in day.items
        if item.place_id is not None
    }
    assert scheduled_by_role["breakfast_meal"].place_id == "coffee-only"
    assert scheduled_by_role["lunch_meal"].place_id == "local-lunch"
    assert scheduled_by_role["support_activity"].place_id == "gallery"
    assert scheduled_by_role["dinner_meal"].place_id == "local-dinner"
    assert all(item.place_id != "hotel" for item in day.items)
    assert all(
        item.notes != "Selected by deterministic Finder candidate loop."
        for item in day.items
    )
    meal_queries = [
        query
        for query in tool.search_queries
        if "local cuisine" in query
    ]
    assert len(meal_queries) == 3
    assert all("món địa phương" in query for query in meal_queries)
    assert all("culture" not in query for query in meal_queries)
    assert all("Culture and food" not in query for query in meal_queries)
    assert all("Hoàn Kiếm" not in query for query in meal_queries)
    assert 25 in tool.search_limits
    assert not any("unresolved meal placeholder" in warning for warning in result.warnings)


def test_food_support_prefers_snack_stop_and_is_reserved_from_meals() -> None:
    restaurant = _place(
        "restaurant",
        "Full meal restaurant",
        tags=["food", "restaurant"],
        intensity=None,
        place_type="restaurant",
    )
    snack_cafe = _place(
        "snack-cafe",
        "Dessert and snack cafe",
        tags=["food", "snack", "dessert"],
        intensity=None,
        place_type="cafe",
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "selected-main": _place(
                    "selected-main",
                    "Main attraction",
                    tags=["culture"],
                    intensity="light",
                ),
                "restaurant": restaurant,
                "snack-cafe": snack_cafe,
            },
            search_order=["restaurant", "snack-cafe"],
        )
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Main attraction",
                mustVisit=True,
                tags=["culture"],
            )
        ],
    )

    support = next(
        item
        for item in result.days[0].items
        if item.role == "support_activity"
    )
    assert support.place_id == "snack-cafe"
    scheduled_ids = [
        item.place_id
        for item in result.days[0].items
        if item.place_id is not None
    ]
    assert scheduled_ids.count("snack-cafe") == 1


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
    finder = FinderService(
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
        item
        for item in result.days[0].items
        if item.role == "support_activity"
    )
    assert support.place_id == "near-culture"


def test_finder_selects_all_activities_before_meals() -> None:
    class RecordingSelector:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        @staticmethod
        def block_is_available(block, user_status) -> bool:
            return True

        def select(self, context):
            destination_ref = (
                context.corridor_destination.stable_ref
                if context.corridor_destination is not None
                else None
            )
            self.calls.append((context.block.role, destination_ref))
            is_meal = context.block.kind == "meal"
            return FinderPlace(
                placeId=context.block.role,
                name=context.block.role,
                placeType="restaurant" if is_meal else "museum",
                regionKey="vn,ha-noi,hoan-kiem",
                tags=["food"] if is_meal else ["culture"],
                latitude=21.03,
                longitude=105.85,
                typicalDurationMinutes=60,
                activityIntensity=None if is_meal else "light",
            )

    selector = RecordingSelector()
    finder = FinderService(
        FakeFinderPlaceTool({}, search_order=[]),
        candidate_selector=selector,  # type: ignore[arg-type]
    )

    result = finder.fill_main_plan(_macro_plan(), _intent(), [])

    assert [role for role, _ in selector.calls] == [
        "main_activity",
        "support_activity",
        "breakfast_meal",
        "lunch_meal",
        "dinner_meal",
    ]
    assert selector.calls[2][1] == "main_activity"
    assert selector.calls[3][1] == "support_activity"
    assert selector.calls[4][1] is None
    assert len(
        [item for item in result.days[0].items if item.timeline_category == "activity"]
    ) == 2


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
    finder = FinderService(
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
        allow_finder_suggestions=False,
    )

    activity_items = [
        item
        for item in result.days[0].items
        if item.source in {"selected_place", "finder_suggestion"}
    ]
    assert [item.name for item in activity_items] == ["Place from OCR"]
    assert all(item.source != "finder_suggestion" for item in activity_items)


def test_reference_only_mode_leaves_unallocated_days_empty() -> None:
    finder = FinderService(
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
    macro_plan = MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
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
        allow_finder_suggestions=False,
    )

    assert result.days[0].strategy == "reference_only"
    assert result.days[0].items == []


def test_reference_intake_fills_missing_activity_before_empty_days() -> None:
    source = _place(
        "source-place",
        "Place from video",
        tags=["culture"],
        intensity="light",
    )
    catalog = _place(
        "catalog-place",
        "Finder suggestion",
        tags=["culture"],
        intensity="light",
        place_type="attraction",
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "source-place": source,
                "catalog-place": catalog,
            },
            search_order=["catalog-place"],
        )
    )
    macro_plan = MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="From video",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture"],
                allocatedSelectedPlaceRefs=["source-place"],
            ),
            DayBrief(
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
                placeId="source-place",
                name="Place from video",
                sourceRefs=["https://example.com/reel"],
                sourceProvider="nominatim",
                sourceOrder=1,
                tags=["culture"],
            )
        ],
        allow_finder_suggestions=True,
    )

    assert [
        item.name
        for item in result.days[0].items
        if item.source == "selected_place"
    ] == ["Place from video"]
    source_item = next(
        item
        for item in result.days[0].items
        if item.source == "selected_place"
    )
    assert source_item.source_provider == "nominatim"
    assert any(
        item.source == "finder_suggestion"
        for item in result.days[0].items
    )
    assert not any(
        item.source == "finder_suggestion"
        for item in result.days[1].items
    )


def test_finder_deduplicates_catalog_alias_against_url_place() -> None:
    source = _place(
        "source-cafe",
        "Train Street",
        tags=["culture"],
        intensity="light",
        latitude=21.0291,
        longitude=105.8412,
    )
    duplicate = _place(
        "catalog-cafe",
        "Ha Noi Train Street",
        tags=["culture"],
        intensity="light",
        latitude=21.0292,
        longitude=105.8413,
    )
    unique = _place(
        "catalog-museum",
        "Womens Museum",
        tags=["culture"],
        intensity="light",
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                source.place_id: source,
                duplicate.place_id: duplicate,
                unique.place_id: unique,
            },
            search_order=[duplicate.place_id, unique.place_id],
        )
    )
    macro_plan = MacroPlan(
        title="Ha Noi",
        destination="Ha Noi",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="URL stops",
                targetArea="Ha Noi",
                targetRegionKey="vn,ha-noi",
                allocatedSelectedPlaceRefs=[source.place_id],
            ),
            DayBrief(
                day=2,
                theme="Finder fill",
                targetArea="Ha Noi",
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
        allow_finder_suggestions=True,
    )

    names = [item.name for day in result.days for item in day.items]
    assert source.name in names
    assert duplicate.name not in names
    assert unique.name in names


def test_low_user_capacity_keeps_fixed_day_frame() -> None:
    finder = FinderService(FakeFinderPlaceTool({}, search_order=[]))
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

    assert result.days[0].strategy == "two_activity_day"
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
    finder = FinderService(
        FakeFinderPlaceTool({"selected-heavy": heavy}, search_order=[]),
    )
    user_status = UserStatus.model_validate(
        {
            "constraints": {
                "allowedActivityIntensities": ["light"]
            }
        }
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
    assert result.unscheduled_places[0].reason_code == "no_available_slot"


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
    finder = FinderService(tool)
    macro_plan = MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
                day=1,
                theme="Food",
                targetArea="Hoàn Kiếm",
                targetRegionKey="vn,ha-noi,hoan-kiem",
                focusTags=["food"],
            ),
            DayBrief(
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

    assert all(
        item.place_id != "selected-day-2"
        for item in result.days[0].items
    )
    assert any(
        item.place_id == "selected-day-2"
        for item in result.days[1].items
    )


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
    finder = FinderService(
        FakeFinderPlaceTool(
            {"closed-morning": closed_morning, "backup": backup},
            search_order=["closed-morning", "backup"],
        )
    )

    result = finder.fill_main_plan(_macro_plan(), _intent(), [])

    assert next(
        item for item in result.days[0].items if item.place_id is not None
    ).name == "Morning museum"
    assert "closed-morning" in result.final_plan_status.rejected_candidate_ids


def test_finder_schedules_place_at_first_feasible_time_inside_soft_window() -> None:
    museum = _place(
        "opens-at-nine",
        "Museum opening at nine",
        tags=["culture", "museum"],
        intensity="light",
        opening_hours=[{"openTime": "09:00", "closeTime": "17:00"}],
    )
    base_brief = _macro_plan().day_briefs[0].model_dump(by_alias=True)
    base_brief.update(
        {
            "allocatedSelectedPlaceRefs": [],
            "dayWindow": {
                            "earliestStart": "08:30",
                            "latestEnd": "20:30",
                        },
            "activityNeeds": [
                            {
                                "role": "main",
                                "goal": "Visit a museum",
                                "preferredExperiences": ["museum"],
                                "minDurationMinutes": 60,
                                "maxDurationMinutes": 120,
                                "required": True,
                            }
                        ],
            "mealNeeds": [
                            {
                                "role": "lunch",
                                "earliestStart": "11:30",
                                "latestEnd": "13:30",
                            },
                            {
                                "role": "dinner",
                                "earliestStart": "17:30",
                                "latestEnd": "20:00",
                            },
            ],
        }
    )
    macro = _macro_plan().model_copy(
        update={"day_briefs": [DayBrief.model_validate(base_brief)]}
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {"opens-at-nine": museum},
            search_order=["opens-at-nine"],
        )
    )

    result = finder.fill_main_plan(macro, _intent(), [])

    item = next(
        item for item in result.days[0].items if item.place_id == "opens-at-nine"
    )
    assert item.time_window == "09:00-10:00"


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
    finder = FinderService(
        FakeFinderPlaceTool(
            {"outdoor": outdoor, "indoor": indoor},
            search_order=["outdoor", "indoor"],
        )
    )
    intent = _intent().model_copy(update={"constraints": ["bad_weather"]})

    result = finder.fill_main_plan(_macro_plan(), intent, [])

    assert result.days[0].strategy == "two_activity_day"
    assert next(
        item for item in result.days[0].items if item.place_id is not None
    ).name == "Indoor gallery"
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
    finder = FinderService(
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

    assert next(
        item for item in result.days[0].items if item.place_id is not None
    ).place_id == "coastal"
    assert "cemetery" in result.final_plan_status.rejected_candidate_ids


def test_constraint_policy_reports_inland_selected_place_as_unscheduled() -> None:
    inland = _place(
        "inland",
        "Bảo tàng nội đô",
        tags=["culture"],
        intensity="light",
    )
    finder = FinderService(
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
            "day_briefs": [
                _macro_plan().day_briefs[0].model_copy(
                    update={"allocated_selected_place_refs": ["inland"]}
                )
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
        places: dict[str, FinderPlace],
        *,
        search_order: list[str],
    ) -> None:
        self.places = places
        self.search_order = search_order
        self.search_queries: list[list[str]] = []
        self.search_limits: list[int] = []

    def get(self, place_id: str) -> FinderPlace | None:
        return self.places.get(place_id)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        target_categories: set[str] | None = None,
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[FinderPlace]:
        self.search_queries.append(list(target_tags))
        self.search_limits.append(limit)
        return [
            self.places[place_id]
            for place_id in self.search_order
            if place_id not in excluded_place_ids
        ][:limit]


def _macro_plan() -> MacroPlan:
    return MacroPlan(
        title="Hà Nội",
        destination="Hà Nội",
        regionKey="vn,ha-noi",
        dayBriefs=[
            DayBrief(
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
) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
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


def test_source_itinerary_uses_fixed_two_activity_frame() -> None:
    macro = _macro_plan().model_copy(
        update={
            "day_briefs": [
                _macro_plan().day_briefs[0].model_copy(
                    update={
                        "allocated_selected_place_refs": ["late-1", "late-2"]
                    }
                )
            ]
        }
    )
    result = FinderService().fill_main_plan(
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
        allow_finder_suggestions=False,
    )

    assert [
        item.name
        for item in result.days[0].items
        if item.source == "selected_place"
    ] == ["Late place 1", "Late place 2"]
    assert result.unscheduled_places == []
    assert all(
        int(item.time_window[:2]) < 24
        and int(item.time_window.split("-", 1)[1][:2]) < 24
        for item in result.days[0].items
    )
