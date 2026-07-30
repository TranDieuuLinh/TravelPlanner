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
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.finder.place_tool import FinderPlace


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
    ]
    assert day.items[0].source == "selected_place"
    assert day.items[2].source == "finder_suggestion"
    assert day.items[2].notes == (
        "Địa điểm phù hợp với lịch trình và sở thích của bạn."
    )
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
    assert result.final_user_status.metrics.energy == 75
    assert result.final_user_status.location is not None
    assert result.final_user_status.location.place_id == "hotel-a"
    assert result.unscheduled_places == []


def test_finder_uses_place_descriptions_for_url_and_suggested_items() -> None:
    source = _place(
        "selected-main",
        "Place from URL",
        tags=["culture"],
        intensity="light",
        description="Không gian trưng bày nghệ thuật Việt Nam.",
    )
    suggestion = _place(
        "suggestion",
        "Suggested café",
        tags=["food"],
        intensity="light",
        place_type="restaurant",
        description="Quán cà phê yên tĩnh với không gian xanh.",
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {"selected-main": source, "suggestion": suggestion},
            search_order=["suggestion"],
        )
    )

    source_result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [
            SelectedPlaceContext(
                placeId="selected-main",
                name="Place from URL",
                sourceRefs=["https://example.com/video"],
                notes="Gợi ý xem bộ sưu tập mỹ thuật hiện đại.",
                tags=["culture"],
            )
        ],
        allow_finder_suggestions=False,
    )
    source_item = next(
        item
        for item in source_result.days[0].items
        if item.source == "selected_place"
    )
    assert source_item.notes == (
        "Gợi ý xem bộ sưu tập mỹ thuật hiện đại."
    )

    suggestion_result = finder.fill_main_plan(_macro_plan(), _intent(), [])
    suggestion_item = next(
        item
        for item in suggestion_result.days[0].items
        if item.source == "finder_suggestion"
    )
    assert suggestion_item.notes == (
        "Quán cà phê yên tĩnh với không gian xanh."
    )


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


def test_reference_intake_supplements_empty_and_sparse_requested_days() -> None:
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
    second_catalog = _place(
        "catalog-place-2",
        "Second Finder suggestion",
        tags=["culture"],
        intensity="light",
    )
    third_catalog = _place(
        "catalog-place-3",
        "Third Finder suggestion",
        tags=["culture"],
        intensity="light",
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "source-place": source,
                "catalog-place": catalog,
                "catalog-place-2": second_catalog,
                "catalog-place-3": third_catalog,
            },
            search_order=[
                "catalog-place",
                "catalog-place-2",
                "catalog-place-3",
            ],
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
                sourceOrder=1,
                tags=["culture"],
            )
        ],
        allow_finder_suggestions=True,
    )

    source_day_activities = [
        item
        for item in result.days[0].items
        if item.place_id is not None
    ]
    assert source_day_activities[0].name == "Place from video"
    assert len(source_day_activities) == 3
    assert sum(
        item.source == "finder_suggestion"
        for item in source_day_activities
    ) == 2
    assert result.days[0].strategy == "source_itinerary_supplemented"
    assert any(
        item.source == "finder_suggestion"
        for item in result.days[1].items
    )


def test_reference_intake_does_not_supplement_a_full_source_day() -> None:
    source_places = [
        _place(
            f"source-{index}",
            f"Source place {index}",
            tags=["culture"],
            intensity="light",
        )
        for index in range(1, 4)
    ]
    catalog = _place(
        "catalog-place",
        "Finder suggestion",
        tags=["culture"],
        intensity="light",
    )
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                **{
                    place.place_id: place
                    for place in source_places
                    if place.place_id is not None
                },
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
                theme="Full source day",
                targetArea="Hà Nội",
                targetRegionKey="vn,ha-noi",
                focusTags=["culture"],
                allocatedSelectedPlaceRefs=[
                    "source-1",
                    "source-2",
                    "source-3",
                ],
            )
        ],
    )

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                placeId=f"source-{index}",
                name=f"Source place {index}",
                sourceRefs=["https://example.com/reel"],
                sourceOrder=index,
                tags=["culture"],
            )
            for index in range(1, 4)
        ],
        allow_finder_suggestions=True,
    )

    assert result.days[0].strategy == "source_itinerary"
    assert all(
        item.source != "finder_suggestion"
        for item in result.days[0].items
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

    def get(self, place_id: str) -> FinderPlace | None:
        return self.places.get(place_id)

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
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
    description: str | None = None,
) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
        placeType=place_type,
        regionKey="vn,ha-noi,hoan-kiem",
        description=description,
        tags=tags,
        latitude=21.03,
        longitude=105.85,
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
