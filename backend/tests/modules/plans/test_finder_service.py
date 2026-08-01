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


def test_finder_uses_dynamic_skeleton_and_retries_candidates() -> None:
    places = {
        "selected-main": _place(
            "selected-main",
            "Selected museum",
            tags=["culture"],
            intensity="moderate",
        ),
        "support": _place(
            "support",
            "Local restaurant",
            tags=["food"],
            intensity="light",
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
        "main_activity",
        "lunch_meal",
        "support_activity",
        "break_support_bonus",
        "dinner_meal",
        "group_social_activity",
    ]
    assert day.items[0].source == "selected_place"
    assert day.items[2].source == "finder_suggestion"
    assert result.final_plan_status.used_place_ids == [
        "selected-main",
        "support",
    ]
    assert result.final_plan_status.rejected_candidate_ids == ["too-heavy"]
    assert result.final_plan_status.visited_tag_counts == {
        "culture": 1,
        "food": 1,
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
    assert scheduled_by_role["lunch_meal"].place_id == "local-lunch"
    assert scheduled_by_role["support_activity"].place_id == "gallery"
    assert scheduled_by_role["dinner_meal"].place_id == "local-dinner"
    assert all(item.place_id != "hotel" for item in day.items)
    assert all(
        item.notes != "Selected by deterministic Finder candidate loop."
        for item in day.items
    )
    social = next(
        item for item in day.items if item.role == "group_social_activity"
    )
    assert "-" in social.time_window
    assert social.notes == "Tính năng gợi ý hoạt động nhóm sẽ sớm ra mắt."
    meal_queries = [
        query
        for query in tool.search_queries
        if "local cuisine" in query
    ]
    assert len(meal_queries) == 2
    assert all("món địa phương" in query for query in meal_queries)
    assert not any("unresolved meal placeholder" in warning for warning in result.warnings)


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
        if item.source != "break"
    ] == ["Place from video"]
    assert result.days[0].items[0].source_provider == "nominatim"
    assert any(
        item.source == "finder_suggestion"
        for item in result.days[1].items
    )


def test_low_user_capacity_switches_day_to_relaxed_skeleton() -> None:
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

    assert result.days[0].strategy == "relaxed"
    assert [item.role for item in result.days[0].items] == [
        "lunch_meal",
        "break_main_support",
        "dinner_meal",
        "group_social_activity",
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

    assert result.days[0].items[0].name == "Morning museum"
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
    finder = FinderService(
        FakeFinderPlaceTool(
            {"outdoor": outdoor, "indoor": indoor},
            search_order=["outdoor", "indoor"],
        )
    )
    intent = _intent().model_copy(update={"constraints": ["bad_weather"]})

    result = finder.fill_main_plan(_macro_plan(), intent, [])

    assert result.days[0].strategy == "indoor_safe"
    assert result.days[0].items[0].name == "Indoor gallery"
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

    assert result.days[0].items[0].place_id == "coastal"
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

    def get(self, place_id: str) -> FinderPlace | None:
        return self.places.get(place_id)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
        bbox_filter: tuple[float, float, float, float] | None = None,
    ) -> list[FinderPlace]:
        self.search_queries.append(list(target_tags))
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


def test_finder_leaves_route_aware_midnight_overflow_unscheduled() -> None:
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

    assert [item.name for item in result.days[0].items] == ["Late place 1"]
    assert result.unscheduled_places[0].name == "Late place 2"
    assert result.unscheduled_places[0].reason_code == "timeline_overflow"
    assert all(
        int(item.time_window[:2]) < 24
        and int(item.time_window.split("-", 1)[1][:2]) < 24
        for item in result.days[0].items
    )
