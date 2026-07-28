from __future__ import annotations

from app.modules.plans.domain.entities import (
    DayBrief,
    MacroPlan,
    TravelIntent,
    UserStatus,
)
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import SelectedPlaceContext
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    FinderAgentInput,
    PlanningIntent,
    TripPlanningSpec,
)
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
        "break_main_support",
        "support_activity",
        "break_support_bonus",
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
    assert result.final_user_status.metrics.energy == 75
    assert result.final_user_status.location is not None
    assert result.final_user_status.location.place_id == "hotel-a"
    assert result.unscheduled_places == []


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
        "break_main_support"
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


def test_finder_agent_contract_wraps_result_and_trace() -> None:
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "selected-main": _place(
                    "selected-main",
                    "Selected museum",
                    tags=["culture"],
                    intensity="moderate",
                )
            },
            search_order=[],
        )
    )

    output = finder.fill_agent_plan(
        FinderAgentInput(
            intent=PlanningIntent(
                destination="Hà Nội",
                budgetLevel="medium",
                pace="balanced",
                interests=["culture"],
            ),
            tripSpec=TripPlanningSpec(days=1),
            macroPlan=AgentMacroPlan.model_validate(_macro_plan().model_dump()),
            selectedPlaces=[
                SelectedPlaceContext(
                    placeId="selected-main",
                    name="Selected museum",
                    mustVisit=True,
                )
            ],
        )
    )

    assert output.final_days[0].items[0].place_id == "selected-main"
    assert output.trip_cost_estimate is None
    assert output.trace.status.value == "completed"
    assert output.trace.notes == [
        "committedPlaceCount=1",
        "unscheduledPlaceCount=0",
    ]


def test_finder_rejects_avoided_and_overlong_candidates() -> None:
    tool = FakeFinderPlaceTool(
        {
            "avoid": _place(
                "avoid",
                "Avoid Me",
                tags=["culture"],
                intensity="light",
                duration=60,
            ),
            "too-long": _place(
                "too-long",
                "Too Long",
                tags=["culture"],
                intensity="light",
                duration=240,
            ),
        },
        search_order=["avoid", "too-long"],
    )
    finder = FinderService(tool)

    output = finder.fill_agent_plan(
        FinderAgentInput(
            intent=PlanningIntent(
                destination="Hà Nội",
                budgetLevel="medium",
                pace="balanced",
                interests=["culture"],
                avoidPlaces=["Avoid Me"],
            ),
            tripSpec=TripPlanningSpec(days=1),
            macroPlan=AgentMacroPlan.model_validate(_macro_plan().model_dump()),
        )
    )

    assert all(
        item.place_id is None
        for item in output.final_days[0].items
    )
    assert output.trace.status.value == "blocked"
    assert output.final_plan_status.rejected_candidate_ids == [
        "avoid",
        "too-long",
    ]


def test_finder_respects_availability_and_user_constraints() -> None:
    tool = FakeFinderPlaceTool(
        {
            "accessible": FinderPlace(
                placeId="accessible",
                name="Accessible museum",
                placeType="museum",
                regionKey="vn,ha-noi,hoan-kiem",
                tags=["culture"],
                typicalDurationMinutes=60,
                activityIntensity="light",
                accessibilityFeatures=["wheelchair"],
            )
        },
        search_order=["accessible"],
    )
    finder = FinderService(tool)
    user_status = UserStatus.model_validate(
        {
            "availableAt": "15:00",
            "constraints": {
                "maxConsecutiveActiveMinutes": 90,
                "requiredRestMinutes": 120,
                "maxWalkingMinutesPerDay": 30,
                "accessibilityNeeds": ["wheelchair"],
            },
        }
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [],
        user_status=user_status,
    )

    activity_items = [
        item
        for item in result.days[0].items
        if item.place_id
    ]
    assert [item.time_window for item in activity_items] == ["17:00-19:00"]
    assert any("only available at 15:00" in item for item in result.warnings)
    assert any("walking-limit feasibility" in item for item in result.warnings)
    assert result.final_user_status.available_at is None


def test_finder_does_not_fabricate_place_id_for_name_only_selection() -> None:
    finder = FinderService(FakeFinderPlaceTool({}, search_order=[]))
    macro_plan = _macro_plan()
    macro_plan.day_briefs[0].allocated_selected_place_refs = [
        "Manual Place"
    ]

    result = finder.fill_main_plan(
        macro_plan,
        _intent(),
        [
            SelectedPlaceContext(
                name="Manual Place",
                mustVisit=False,
                sourceRefs=["source-manual"],
                tags=["local"],
            )
        ],
    )

    item = next(
        item
        for item in result.days[0].items
        if item.source == "selected_place"
    )
    assert item.place_id is None
    assert item.place_type == "selected_place"
    assert item.source_refs == ["source-manual"]
    assert item.tags == ["local"]
    assert result.final_plan_status.used_place_ids == ["Manual Place"]


def test_finder_rejects_unverified_accessibility_match() -> None:
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "unknown-access": _place(
                    "unknown-access",
                    "Unknown access",
                    tags=["culture"],
                    intensity="light",
                )
            },
            search_order=["unknown-access"],
        )
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [],
        user_status=UserStatus.model_validate(
            {
                "constraints": {
                    "accessibilityNeeds": ["wheelchair"],
                }
            }
        ),
    )

    assert result.final_plan_status.used_place_ids == []
    assert result.final_plan_status.rejected_candidate_ids == [
        "unknown-access"
    ]


def test_finder_respects_max_consecutive_activity_minutes() -> None:
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "one-hour": _place(
                    "one-hour",
                    "One-hour activity",
                    tags=["culture"],
                    intensity="light",
                    duration=60,
                )
            },
            search_order=["one-hour"],
        )
    )

    result = finder.fill_main_plan(
        _macro_plan(),
        _intent(),
        [],
        user_status=UserStatus.model_validate(
            {
                "constraints": {
                    "maxConsecutiveActiveMinutes": 30,
                }
            }
        ),
    )

    assert result.final_plan_status.used_place_ids == []
    assert result.final_plan_status.rejected_candidate_ids == ["one-hour"]


def test_finder_avoid_outdoor_uses_type_and_tags() -> None:
    finder = FinderService(
        FakeFinderPlaceTool(
            {
                "beach": FinderPlace(
                    placeId="beach",
                    name="Coastal Stop",
                    placeType="beach",
                    regionKey="vn,ha-noi,hoan-kiem",
                    tags=["outdoor"],
                    typicalDurationMinutes=60,
                    activityIntensity="light",
                ),
                "indoor": FinderPlace(
                    placeId="indoor",
                    name="Park Museum",
                    placeType="museum",
                    regionKey="vn,ha-noi,hoan-kiem",
                    tags=["indoor", "culture"],
                    typicalDurationMinutes=60,
                    activityIntensity="light",
                ),
            },
            search_order=["beach", "indoor"],
        )
    )

    output = finder.fill_agent_plan(
        FinderAgentInput(
            mode="backup",
            intent=PlanningIntent(
                destination="Hà Nội",
                budgetLevel="medium",
                constraints=["avoid_outdoor"],
            ),
            tripSpec=TripPlanningSpec(days=1),
            macroPlan=AgentMacroPlan.model_validate(_macro_plan().model_dump()),
        )
    )

    activity_names = [
        item.name
        for item in output.final_days[0].items
        if item.place_id
    ]
    assert "Coastal Stop" not in activity_names
    assert "Park Museum" in activity_names
    assert output.final_plan_status.rejected_candidate_ids == ["beach"]


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
) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
        placeType="attraction",
        regionKey="vn,ha-noi,hoan-kiem",
        tags=tags,
        latitude=21.03,
        longitude=105.85,
        typicalDurationMinutes=duration,
        activityIntensity=intensity,
        dataConfidence="high",
    )
