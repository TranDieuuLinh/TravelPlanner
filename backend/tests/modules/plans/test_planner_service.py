from __future__ import annotations

import asyncio
import json

import pytest

from app.modules.places.auto_statistics.service import (
    PlannerRegionStatisticsResult,
)
from app.modules.plans.domain.entities import TravelIntent
from app.modules.plans.domain.enums import BudgetLevel, TravelPace
from app.modules.plans.dto.agent_contracts import (
    PlanWorkingState,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.planner.region_context import (
    normalize_region_key,
    normalize_search_region_key,
)
from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.schema import (
    BackupPlanCreate,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanningContextCreate,
    SelectedPlaceCreate,
)
from app.modules.plans.repository import PlanRepository
from app.modules.plans.service import PlanService, _merge_selected_places
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.shared.errors import AppError


@pytest.mark.parametrize(
    "destination",
    [
        "Hanoi",
        "Ha Noi",
        "Hà Nội",
        "HaNoi",
        "HN",
        "Hanoi, Vietnam",
        "Hanoi, Viet Nam",
        "Ha Noi, Vietnam",
        "Hà Nội, Việt Nam",
        "Vietnam, Hanoi",
        "Việt Nam - Hà Nội",
        "Hanoi City, Vietnam",
        "Thành phố Hà Nội, Việt Nam",
        "TP. Hà Nội",
    ],
)
def test_normalize_region_key_from_hanoi_aliases(destination: str) -> None:
    assert normalize_region_key(destination) == "vn,ha-noi"


def test_normalize_region_key_canonicalizes_explicit_hanoi_alias() -> None:
    assert normalize_region_key("ignored", "vn,hanoi") == "vn,ha-noi"
    assert (
        normalize_region_key("ignored", "vn,hanoi-vietnam,hoan-kiem")
        == "vn,ha-noi,hoan-kiem"
    )
    assert normalize_region_key("ignored", "vn,hai-phong") == "vn,hai-phong"


@pytest.mark.parametrize(
    ("search_region", "destination", "expected"),
    [
        ("Tây Hồ", "Hanoi", "vn,ha-noi,tay-ho"),
        ("Tay Ho District", "Hà Nội", "vn,ha-noi,tay-ho"),
        ("Tây Hồ, Hà Nội", "Ha Noi", "vn,ha-noi,tay-ho"),
        ("Hanoi, Tay Ho", "Hà Nội", "vn,ha-noi,tay-ho"),
        ("Hà Nội", "Hanoi", "vn,ha-noi"),
        ("Ninh Bình", "Hanoi", "vn,ninh-binh"),
        ("Danang", "Hanoi", "vn,da-nang"),
        ("Saigon", "Hanoi", "vn,ho-chi-minh"),
    ],
)
def test_normalize_search_region_key_preserves_roots_and_scopes_areas(
    search_region: str,
    destination: str,
    expected: str,
) -> None:
    assert normalize_search_region_key(search_region, destination) == expected


def test_main_workflow_uses_canonical_hanoi_catalog_region() -> None:
    statistics = FakeStatisticsProvider()
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(statistics),
        finder=FinderService(),
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hanoi, Vietnam",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture"],
            },
            "tripSpec": {"days": 1},
            "selectedPlaces": [],
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    assert statistics.requested_region_keys == ["vn,ha-noi"]
    assert plan.macro_plan.region_key == "vn,ha-noi"


def test_city_stay_spans_two_empty_days_without_becoming_place() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider()),
        finder=FinderService(),
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hanoi",
                "travelStyle": "local",
                "pace": "balanced",
                "destinationStays": [
                    {
                        "name": "Hanoi",
                        "durationDays": 2,
                        "startDay": 1,
                        "endDay": 2,
                        "sourceRefs": [
                            "https://www.instagram.com/reel/example"
                        ],
                    }
                ],
            },
            "tripSpec": {"days": 2},
            "selectedPlaces": [],
            "allowFinderSuggestions": False,
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    assert [brief.target_area for brief in plan.macro_plan.day_briefs] == [
        "Hanoi",
        "Hanoi",
    ]
    assert len(plan.days) == 2
    assert all(day.items == [] for day in plan.days)
    assert all("Hanoi" in day.theme for day in plan.days)


def test_planner_uses_snapshot_and_accounts_for_selected_places() -> None:
    statistics = FakeStatisticsProvider()
    service = _planner(statistics)
    selected_places = [
        SelectedPlaceContext(
            name="Văn Miếu",
            placeId="place-van-mieu",
            mustVisit=True,
            priority=1,
        ),
        SelectedPlaceContext(
            name="Bỏ qua",
            placeId="place-excluded",
            priority=2,
        ),
    ]

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=selected_places,
            plan_state=PlanWorkingState(excludedPlaceNames=["Bỏ qua"]),
        )
    )

    assert statistics.requested_region_keys == ["vn,ha-noi"]
    assert output.day_briefs_ready is True
    assert "snapshotRef" not in output.macro_plan.model_dump(by_alias=True)
    assert "generator=llm" in output.trace.notes
    assert "researchPromptVersion=journey_research_v2" in output.trace.notes
    assert "promptVersion=trip_theme_planner_v4" in output.trace.notes
    assert "snapshotId=snapshot-3" in output.trace.notes
    assert output.macro_plan.day_briefs[0].target_region_key == (
        "vn,ha-noi,hoan-kiem"
    )
    assert output.macro_plan.day_briefs[0].focus_tags[:2] == [
        "culture",
        "food",
    ]
    assert output.macro_plan.day_briefs[0].allocated_selected_place_refs == [
        "place-van-mieu"
    ]
    assert output.unallocated_selected_places[0].place.place_id == (
        "place-excluded"
    )
    assert output.unallocated_selected_places[0].reason_code == (
        "excluded_by_plan_state"
    )
    assert output.assumptions == ["Generated by test LLM."]


def test_url_itinerary_respects_pace_capacity_and_keeps_source_order() -> None:
    statistics = FakeStatisticsProvider(place_count=0)
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(statistics),
        finder=FinderService(),
    )
    source_places = [
        SelectedPlaceCreate(
            name=name,
            latitude=21.02 + index / 1000,
            longitude=105.82 + index / 1000,
            sourceRefs=["https://example.com/hanoi-reel"],
            sourceOrder=index,
            sourceDay=1,
            sourceTimeHint=time_hint,
            sourceActivity=activity,
            sourceDurationMinutes=45,
            notes=(
                "Đã định vị theo địa chỉ; chưa xác minh POI cụ thể."
                if index == 1
                else None
            ),
        )
        for index, (name, time_hint, activity) in enumerate(
            [
                ("Xôi Yến", "breakfast", "Order turmeric sticky rice."),
                ("Cafe Phố Cổ", "morning", "Order an egg coffee."),
                ("Hoàn Kiếm Lake", "morning", "Walk around the lake."),
                ("Ngọc Sơn Temple", "morning", "Visit the temple."),
                ("Cooking class", "before lunch", "Join the market visit."),
                ("Hỏa Lò Prison", "afternoon", "Learn about its history."),
                ("Train Street", "after dinner", "Visit a valid entrance."),
            ],
            start=1,
        )
    ]
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "pace": "balanced",
                "interests": ["food", "culture"],
            },
            "tripSpec": {"days": 1},
            "selectedPlaces": [
                place.model_dump(mode="json", by_alias=True)
                for place in reversed(source_places)
            ],
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    assert plan.days[0].strategy == "source_itinerary"
    assert [item.name for item in plan.days[0].items] == [
        place.name for place in source_places[:2]
    ]
    assert [item.name for item in plan.unscheduled_places] == [
        place.name for place in source_places[2:]
    ]
    assert {
        item.reason_code for item in plan.unscheduled_places
    } == {"no_day_capacity"}
    assert [item.source_order for item in plan.days[0].items] == [1, 2]
    assert plan.days[0].items[0].place_id is None
    assert plan.days[0].items[0].notes == (
        "Đã định vị theo địa chỉ; chưa xác minh POI cụ thể."
    )
    assert plan.days[0].items[1].notes == "Order an egg coffee."
    assert len(plan.days[0].transport_legs) == 1


@pytest.mark.parametrize(
    ("stop_count", "requested_days", "scheduled_count"),
    [(10, 4, 8), (20, 6, 12)],
)
def test_url_itinerary_without_source_days_fills_every_stop(
    stop_count: int,
    requested_days: int,
    scheduled_count: int,
) -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
    )
    places = [
        SelectedPlaceCreate(
            name=f"URL stop {index}",
            sourceRefs=["https://example.com/hanoi-reel"],
            sourceOrder=index,
            sourceDurationMinutes=45,
        )
        for index in range(1, stop_count + 1)
    ]
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "pace": "balanced",
            },
            "tripSpec": {"days": requested_days},
            "selectedPlaces": [
                place.model_dump(mode="json", by_alias=True)
                for place in places
            ],
            "allowFinderSuggestions": False,
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    scheduled = [
        item
        for day in plan.days
        for item in day.items
        if item.source == "selected_place"
    ]
    assert [item.name for item in scheduled] == [
        place.name for place in places[:scheduled_count]
    ]
    assert [item.name for item in plan.unscheduled_places] == [
        place.name for place in places[scheduled_count:]
    ]
    assert all(
        item.reason_code == "no_day_capacity"
        for item in plan.unscheduled_places
    )


def test_planner_marks_day_briefs_not_ready_when_region_is_empty() -> None:
    service = _planner(FakeStatisticsProvider(place_count=0))

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.day_briefs_ready is False
    assert output.trace.status.value == "blocked"
    assert output.warnings == [
        "Không có Place active cho vn,ha-noi; Finder chỉ có thể dùng các "
        "địa điểm người dùng đã chọn."
    ]


def test_planner_sends_small_area_statistics_to_llm() -> None:
    llm = RecordingPlannerLLM()
    service = PlannerService(FakeStatisticsProvider(), llm)

    asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert len(llm.calls) == 2
    assert json.loads(llm.calls[0][1])["stage"] == "research"
    assert "Trip Theme Planner" in llm.system_prompt
    payload = json.loads(llm.user_payload)
    assert payload["stage"] == "macro_plan"
    assert payload["promptVersion"] == "trip_theme_planner_v4"
    assert payload["plannerInput"]["regionContext"]["plannerSignals"][
        "candidateAreas"
    ][0]["regionKey"] == "vn,ha-noi,hoan-kiem"
    assert payload["researchProposal"]["varietyStrategy"]
    assert "verifiedResearch" in payload


def test_trip_theme_planner_projects_requirements_to_neutral_route_buckets() -> None:
    service = PlannerService(FakeStatisticsProvider(), TripThemeOnlyLLM())

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert [theme.theme for theme in output.macro_plan.trip_themes] == [
        "Lịch sử",
        "Nghệ thuật",
    ]
    assert all(
        brief.theme == "Tối ưu theo tuyến"
        for brief in output.macro_plan.day_briefs
    )
    assert all(
        brief.focus_tags == ["history", "art"]
        for brief in output.macro_plan.day_briefs
    )


def test_planner_normalizes_food_themes_and_over_capacity_requirements() -> None:
    service = PlannerService(
        FakeStatisticsProvider(),
        OverCapacityThemesLLM(),
    )

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert [theme.theme for theme in output.macro_plan.trip_themes] == [
        "Văn hóa địa phương"
    ]
    assert output.macro_plan.trip_themes[0].minimum_activities == 2
    assert any("khung bữa ăn riêng" in warning for warning in output.warnings)


def test_planner_can_continue_without_catalog_when_places_are_confirmed() -> None:
    service = _planner(FakeStatisticsProvider(place_count=0))

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[
                SelectedPlaceContext(
                    placeId="place-van-mieu",
                    name="Văn Miếu",
                    mustVisit=True,
                )
            ],
        )
    )

    assert output.day_briefs_ready is True
    assert output.macro_plan.day_briefs[0].allocated_selected_place_refs == [
        "place-van-mieu"
    ]


def test_planner_reports_confirmed_places_over_day_capacity() -> None:
    service = _planner(FakeStatisticsProvider())
    selected_places = [
        SelectedPlaceContext(
            placeId=f"place-{index}",
            name=f"Place {index}",
            mustVisit=True,
        )
        for index in range(1, 8)
    ]

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=selected_places,
        )
    )

    allocated = sum(
        len(day.allocated_selected_place_refs)
        for day in output.macro_plan.day_briefs
    )
    assert allocated == 4
    assert {
        item.place.place_id for item in output.unallocated_selected_places
    } == {"place-5", "place-6", "place-7"}
    assert all(
        item.reason_code == "no_day_capacity"
        for item in output.unallocated_selected_places
    )


def test_planner_does_not_allocate_explicitly_avoided_place() -> None:
    service = _planner(FakeStatisticsProvider())
    intent = _intent().model_copy(
        update={"avoid_places": ["Avoid Me"]}
    )

    output = asyncio.run(
        service.create_main_macro_plan(
            intent,
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[
                SelectedPlaceContext(
                    placeId="avoid-me",
                    name="Avoid Me",
                    mustVisit=True,
                )
            ],
        )
    )

    assert output.macro_plan.day_briefs[0].allocated_selected_place_refs == []
    assert output.unallocated_selected_places[0].place.place_id == "avoid-me"
    assert output.unallocated_selected_places[0].reason_code == "avoided_by_user"


def test_planner_preserves_selected_place_omitted_by_llm() -> None:
    service = PlannerService(
        FakeStatisticsProvider(),
        OmittingSelectedPlaceLLM(),
    )

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[
                SelectedPlaceContext(
                    placeId="place-kept",
                    name="Kept Place",
                    mustVisit=True,
                ),
                SelectedPlaceContext(
                    placeId="place-omitted",
                    name="Omitted Place",
                    mustVisit=True,
                ),
            ],
        )
    )

    assert output.macro_plan.day_briefs[0].allocated_selected_place_refs == [
        "place-kept"
    ]
    assert output.unallocated_selected_places[0].place.place_id == (
        "place-omitted"
    )
    assert output.unallocated_selected_places[0].reason_code == (
        "planner_omitted_selected_place"
    )
    assert any(
        "backend đã giữ" in warning
        for warning in output.warnings
    )


def test_planner_drops_hallucinated_selected_place_reference() -> None:
    llm = HallucinatingSelectedRefLLM()
    service = PlannerService(FakeStatisticsProvider(), llm)

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.macro_plan.day_briefs[0].allocated_selected_place_refs == []
    assert output.unallocated_selected_places == []
    assert any(
        "backend đã loại bỏ" in warning
        for warning in output.warnings
    )
    assert "repairAttempts=0" in output.trace.notes


def test_planner_repairs_invalid_macro_contract_once() -> None:
    llm = RepairingPlannerLLM()
    service = PlannerService(FakeStatisticsProvider(), llm)

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.day_briefs_ready is True
    assert [brief.day for brief in output.macro_plan.day_briefs] == [1, 2]
    assert llm.macro_calls == 2
    assert llm.repair_feedback == (
        "MacroPlan must contain consecutive requested days."
    )


def test_planner_can_repair_invalid_macro_contract_three_times() -> None:
    llm = MultiRepairPlannerLLM(valid_on_macro_call=4)
    service = PlannerService(FakeStatisticsProvider(), llm)

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.day_briefs_ready is True
    assert llm.macro_calls == 4
    assert "repairAttempts=3" in output.trace.notes


def test_planner_stops_after_three_failed_repairs() -> None:
    llm = MultiRepairPlannerLLM(valid_on_macro_call=5)
    service = PlannerService(FakeStatisticsProvider(), llm)

    with pytest.raises(
        RuntimeError,
        match="after 3 repair attempts",
    ):
        asyncio.run(
            service.create_main_macro_plan(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

    assert llm.macro_calls == 4


def test_planner_is_ready_with_confirmed_place_when_region_is_empty() -> None:
    service = _planner(FakeStatisticsProvider(place_count=0))

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[
                SelectedPlaceContext(
                    name="Văn Miếu",
                    placeId="place-van-mieu",
                    mustVisit=True,
                )
            ],
        )
    )

    assert output.day_briefs_ready is True
    assert output.trace.status.value == "completed"


def test_long_road_trip_uses_multiple_journey_phases() -> None:
    service = _planner(FakeStatisticsProvider())

    output = asyncio.run(
        service.create_main_macro_plan(
            _intent().model_copy(
                update={"days": 7, "travel_style": "phượt"}
            ),
            trip_spec=TripPlanningSpec(days=7),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.macro_plan.journey_style == "road_trip"
    assert [
        (phase.start_day, phase.end_day)
        for phase in output.macro_plan.journey_phases
    ] == [(1, 3), (4, 7)]


def test_main_workflow_accepts_structured_selected_places() -> None:
    statistics = FakeStatisticsProvider()
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(statistics),
        finder=FinderService(),
    )
    payload = MainPlanCreate.model_validate(
        {
            "destination": "Hà Nội",
            "days": 2,
            "interests": ["culture"],
            "regionKey": "vn,ha-noi",
            "selectedPlaces": [
                {
                    "placeId": "place-van-mieu",
                    "name": "Văn Miếu",
                    "mustVisit": True,
                    "priority": 1,
                    "tags": ["culture"],
                }
            ],
        }
    )

    plan = asyncio.run(workflow.run(payload))

    assert plan.macro_plan.region_key == "vn,ha-noi"
    assert "snapshotRef" not in plan.macro_plan.model_dump(by_alias=True)
    assert plan.macro_plan.day_briefs[0].allocated_selected_place_refs == [
        "place-van-mieu"
    ]
    assert plan.days[0].items[0].name == "Văn Miếu"


def test_main_workflow_accepts_confirmed_explorer_context() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture"],
            },
            "tripSpec": {
                "days": 2,
                "partySize": 3,
                "budget": {
                    "targetAmount": 6_000_000,
                    "level": "medium",
                },
            },
            "selectedPlaces": [
                {
                    "name": "Văn Miếu",
                    "mustVisit": True,
                    "tags": ["culture"],
                    "sourceRefs": ["https://example.com/reel"],
                }
            ],
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    assert plan.status.value == "draft"
    assert plan.check_report is not None
    assert plan.check_report.status == "needs_backup"
    assert plan.days[0].items[0].name == "Văn Miếu"


def test_plan_service_uses_persisted_explorer_places_from_intake() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
    )
    service = PlanService(
        repository=PlanRepository(),
        explore_formatter=object(),  # type: ignore[arg-type]
        main_workflow=main_workflow,
        backup_workflow=object(),  # type: ignore[arg-type]
        explorer_persistence=FakeExplorerPersistence(),
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intakeId": "intake-tiktok",
            "userId": None,
            "intent": {
                "destination": "Hà Nội",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["food"],
            },
            "tripSpec": {
                "days": 1,
                "partySize": 2,
                "budget": {
                    "targetAmount": None,
                    "level": "medium",
                },
            },
            "selectedPlaces": [],
        }
    )

    plan, timing = asyncio.run(
        service.create_main_plan_from_explorer_with_timing(payload)
    )

    assert plan.days[0].items[0].name == "Bún chả Hàng Quạt"
    assert plan.days[0].items[0].source_refs == [
        "https://www.tiktok.com/@brandneweats/video/7662905162960243989"
    ]
    assert timing.status == "completed"
    assert timing.total_seconds >= 0
    assert [stage.key for stage in timing.stages] == [
        "preparePlanningContext",
        "planner",
        "finder",
        "assemblePlan",
        "checkOverall",
    ]
    assert timing.day_count == len(plan.days)
    assert timing.item_count == sum(len(day.items) for day in plan.days)


def test_plan_service_expands_days_to_fit_merged_selected_places() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider()),
        finder=FinderService(),
    )
    service = PlanService(
        repository=PlanRepository(),
        explore_formatter=object(),  # type: ignore[arg-type]
        main_workflow=main_workflow,
        backup_workflow=object(),  # type: ignore[arg-type]
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "pace": "balanced",
            },
            "tripSpec": {"days": 2},
            "selectedPlaces": [
                {
                    "placeId": f"place-{index}",
                    "name": f"Place {index}",
                }
                for index in range(1, 8)
            ],
            "expandDaysToFitSelectedPlaces": True,
        }
    )

    plan = asyncio.run(service.create_main_plan_from_explorer(payload))

    assert plan.intent.days == 4
    assert len(plan.days) == 4
    assert plan.unscheduled_places == []


def test_merge_selected_places_removes_same_url_identity_variants() -> None:
    source_url = "https://www.tiktok.com/@creator/video/42"
    merged = _merge_selected_places(
        [
            SelectedPlaceCreate(
                name="Phố đường tàu",
                latitude=21.0291,
                longitude=105.8412,
                sourceRefs=[source_url],
                sourceProvider="google_maps_scraper",
            ),
            SelectedPlaceCreate(
                name="Phố đường tàu Hà Nội",
                placeId="train-street",
                latitude=21.0292,
                longitude=105.8413,
                sourceRefs=[source_url],
                sourceProvider="database",
            ),
        ],
        [],
    )

    assert len(merged) == 1
    assert merged[0].name == "Phố đường tàu Hà Nội"
    assert merged[0].place_id == "train-street"


def test_plan_service_expands_days_to_schedule_all_url_places() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider()),
        finder=FinderService(),
    )
    service = PlanService(
        repository=PlanRepository(),
        explore_formatter=object(),  # type: ignore[arg-type]
        main_workflow=main_workflow,
        backup_workflow=object(),  # type: ignore[arg-type]
    )
    source_url = "https://www.tiktok.com/@traveler/video/123456789"
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "pace": "balanced",
            },
            "tripSpec": {"days": 1},
            "selectedPlaces": [
                {
                    "name": f"TikTok Place {index}",
                    "sourceRefs": [source_url],
                    "sourceOrder": index,
                    "sourceDay": 1,
                }
                for index in range(1, 8)
            ],
            "expandDaysToFitSelectedPlaces": True,
        }
    )

    plan = asyncio.run(service.create_main_plan_from_explorer(payload))

    assert plan.intent.days == 4
    assert len(plan.days) == 4
    assert {
        item.name
        for day in plan.days
        for item in day.items
        if item.source == "selected_place"
    } == {f"TikTok Place {index}" for index in range(1, 8)}
    assert plan.unscheduled_places == []


def test_plan_service_keeps_url_overflow_unscheduled_for_fixed_duration() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider()),
        finder=FinderService(),
    )
    service = PlanService(
        repository=PlanRepository(),
        explore_formatter=object(),  # type: ignore[arg-type]
        main_workflow=main_workflow,
        backup_workflow=object(),  # type: ignore[arg-type]
    )
    source_url = "https://www.tiktok.com/@traveler/video/fixed"
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {"destination": "Hà Nội", "pace": "balanced"},
            "tripSpec": {"days": 1},
            "selectedPlaces": [
                {
                    "name": f"TikTok Place {index}",
                    "sourceRefs": [source_url],
                    "sourceOrder": index,
                    "sourceDay": 1,
                }
                for index in range(1, 5)
            ],
            "expandDaysToFitSelectedPlaces": False,
        }
    )

    plan = asyncio.run(service.create_main_plan_from_explorer(payload))

    assert plan.intent.days == 1
    assert len(plan.unscheduled_places) == 2
    assert {item.reason_code for item in plan.unscheduled_places} == {
        "no_day_capacity"
    }


def test_food_url_places_use_meal_slots_before_expanding_days() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider()),
        finder=FinderService(),
    )
    service = PlanService(
        repository=PlanRepository(),
        explore_formatter=object(),  # type: ignore[arg-type]
        main_workflow=main_workflow,
        backup_workflow=object(),  # type: ignore[arg-type]
    )
    source_url = "https://www.tiktok.com/@traveler/video/food"
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {"destination": "Hà Nội", "pace": "balanced"},
            "tripSpec": {"days": 1},
            "selectedPlaces": [
                {
                    "name": f"Restaurant {index}",
                    "tags": ["restaurant"],
                    "sourceRefs": [source_url],
                    "sourceOrder": index,
                    "sourceDay": 1,
                }
                for index in range(1, 5)
            ],
            "expandDaysToFitSelectedPlaces": True,
        }
    )

    plan = asyncio.run(service.create_main_plan_from_explorer(payload))

    assert plan.intent.days == 2
    assert plan.unscheduled_places == []
    selected_food = [
        item
        for day in plan.days
        for item in day.items
        if item.source == "selected_place"
    ]
    assert len(selected_food) == 4
    assert all(item.timeline_category == "food" for item in selected_food)


def test_main_workflow_accepts_planning_context() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
        checker=OverallChecker(),
    )
    payload = PlanningContextCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture"],
            },
            "tripSpec": {
                "days": 2,
                "partySize": 2,
                "budget": {
                    "targetAmount": None,
                    "level": "medium",
                },
            },
            "regionKey": "vn,ha-noi",
            "selectedPlaces": [
                {
                    "placeId": "place-van-mieu",
                    "name": "Văn Miếu",
                    "mustVisit": True,
                    "priority": 1,
                },
                {
                    "placeId": "place-ho-guom",
                    "name": "Hồ Gươm",
                    "mustVisit": True,
                    "priority": 2,
                },
            ],
        }
    )

    plan = asyncio.run(workflow.run_from_context(payload))

    assert plan.intent.days == 2
    assert len(plan.days) == 2
    assert plan.days[0].items[0].place_id == "place-van-mieu"
    assert plan.days[1].items[0].place_id == "place-ho-guom"
    assert plan.status.value == "draft"
    assert plan.check_report is not None
    assert plan.check_report.status == "needs_backup"


def test_main_workflow_keeps_plan_draft_when_place_is_unscheduled() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider()),
        finder=FinderService(),
        checker=OverallChecker(),
    )
    payload = MainPlanCreate.model_validate(
        {
            "destination": "Hà Nội",
            "days": 1,
            "pace": "balanced",
            "regionKey": "vn,ha-noi",
            "selectedPlaces": [
                {
                    "placeId": f"place-{index}",
                    "name": f"Place {index}",
                    "mustVisit": True,
                }
                for index in range(1, 5)
            ],
        }
    )

    plan = asyncio.run(workflow.run(payload))

    assert plan.status.value == "draft"
    assert plan.check_report is not None
    assert plan.check_report.status == "needs_backup"
    assert plan.unscheduled_places[0].place_id == "place-4"
    assert plan.unscheduled_places[0].reason_code == "no_day_capacity"


def test_main_workflow_rejects_empty_catalog_and_no_confirmed_places() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=_planner(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
        checker=OverallChecker(),
    )
    payload = MainPlanCreate(
        destination="Hà Nội",
        days=1,
        selectedPlaces=[],
    )

    with pytest.raises(AppError) as captured:
        asyncio.run(workflow.run(payload))

    assert captured.value.code == "PLANNER_INPUT_INSUFFICIENT"
    assert captured.value.status_code == 422


def test_backup_preserves_optional_confirmed_place() -> None:
    statistics = FakeStatisticsProvider()
    planner = _planner(statistics)
    finder = FinderService()
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=planner,
        finder=finder,
        checker=OverallChecker(),
    )
    backup_workflow = BackupPlanWorkflow(
        planner=planner,
        finder=finder,
        validator=BackupValidator(),
    )
    main_plan = asyncio.run(
        main_workflow.run(
            MainPlanCreate.model_validate(
                {
                    "destination": "Hà Nội",
                    "days": 1,
                    "regionKey": "vn,ha-noi",
                    "selectedPlaces": [
                        {
                            "placeId": "optional-place",
                            "name": "Optional Place",
                            "mustVisit": False,
                            "sourceRefs": ["source-1"],
                            "tags": ["indoor"],
                        }
                    ],
                }
            )
        )
    )

    backup_plan, _ = asyncio.run(
        backup_workflow.run(
            main_plan,
            BackupPlanCreate(reason="test optional preservation"),
        )
    )

    preserved = [
        item
        for day in backup_plan.days
        for item in day.items
        if item.source == "selected_place"
    ]
    assert [item.name for item in preserved] == ["Optional Place"]
    assert preserved[0].source_refs == ["source-1"]
    assert main_plan.days[0].items[0].place_type == "selected_place"


def test_backup_avoid_outdoor_uses_tags_not_place_name() -> None:
    statistics = FakeStatisticsProvider()
    planner = _planner(statistics)
    finder = FinderService()
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=planner,
        finder=finder,
        checker=OverallChecker(),
    )
    backup_workflow = BackupPlanWorkflow(
        planner=planner,
        finder=finder,
        validator=BackupValidator(),
    )
    main_plan = asyncio.run(
        main_workflow.run(
            MainPlanCreate.model_validate(
                {
                    "destination": "Hà Nội",
                    "days": 1,
                    "regionKey": "vn,ha-noi",
                    "selectedPlaces": [
                        {
                            "placeId": "beach-stop",
                            "name": "Coastal Stop",
                            "mustVisit": False,
                            "tags": ["beach", "outdoor"],
                        }
                    ],
                }
            )
        )
    )

    backup_plan, _ = asyncio.run(
        backup_workflow.run(
            main_plan,
            BackupPlanCreate(avoidOutdoor=True),
        )
    )

    assert all(
        item.name != "Coastal Stop"
        for day in backup_plan.days
        for item in day.items
    )
    assert "avoid_outdoor" in backup_plan.intent.constraints


def _planner(statistics: "FakeStatisticsProvider") -> PlannerService:
    return PlannerService(statistics, FakePlannerLLM())


class FakePlannerLLM:
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        planner_input = envelope["plannerInput"]
        intent = planner_input["intent"]
        trip_spec = planner_input["tripSpec"]
        context = planner_input["regionContext"]
        if envelope["stage"] == "research":
            capabilities = [
                interest
                for interest in intent["interests"]
                if interest
                in {
                    "beach",
                    "seafood",
                    "mountain",
                    "hiking",
                    "food",
                    "coffee",
                    "culture",
                    "nature",
                    "nightlife",
                    "camping",
                    "shopping",
                    "wellness",
                }
            ] or ["culture"]
            return json.dumps(
                {
                    "journeyStyle": (
                        "road_trip"
                        if trip_spec["days"] >= 7
                        else "local_base"
                    ),
                    "varietyStrategy": (
                        "Vary themes according to duration and verified evidence."
                    ),
                    "themeQueries": [
                        {
                            "theme": capability,
                            "capabilities": [capability],
                            "preferredRegionKey": context["regionKey"],
                            "rationale": "Verify the proposed theme.",
                        }
                        for capability in capabilities[:4]
                    ],
                    "expandBeyondRoot": trip_spec["days"] >= 7,
                    "nearbyCapabilities": capabilities[:4],
                    "maxDistanceKm": 150,
                },
                ensure_ascii=False,
            )

        selected = sorted(
            planner_input["selectedPlaces"],
            key=lambda place: (
                not place["mustVisit"],
                place["priority"],
                place["name"],
            ),
        )
        capacity = {
            "relaxed": 2,
            "balanced": 3,
            "packed": 5,
        }[intent["pace"]]
        allocation_order = [
            day
            for _ in range(capacity)
            for day in range(1, trip_spec["days"] + 1)
        ]
        allocated_by_day = {
            day: [] for day in range(1, trip_spec["days"] + 1)
        }
        unallocated = []
        avoided = {name.casefold() for name in intent["avoidPlaces"]}
        excluded = {
            name.casefold()
            for name in planner_input["planState"]["excludedPlaceNames"]
        }
        allocation_index = 0
        for place in selected:
            stable_ref = place.get("placeId") or place["name"]
            if place["name"].casefold() in avoided:
                unallocated.append(
                    {
                        "place": place,
                        "reasonCode": "avoided_by_user",
                        "reason": "Place is explicitly avoided.",
                    }
                )
                continue
            if place["name"].casefold() in excluded:
                unallocated.append(
                    {
                        "place": place,
                        "reasonCode": "excluded_by_plan_state",
                        "reason": "Place is excluded from this planning scope.",
                    }
                )
                continue
            if allocation_index >= len(allocation_order):
                unallocated.append(
                    {
                        "place": place,
                        "reasonCode": "no_day_capacity",
                        "reason": "No remaining macro-plan capacity.",
                    }
                )
                continue
            day = allocation_order[allocation_index]
            allocated_by_day[day].append(stable_ref)
            allocation_index += 1

        candidate_areas = context["plannerSignals"].get("candidateAreas", [])
        target_region = (
            candidate_areas[0]["regionKey"]
            if candidate_areas
            else context["regionKey"]
        )
        focus = (
            intent["interests"]
            or context["plannerSignals"].get("dominantTags", [])
            or ["local"]
        )
        day_briefs = [
            {
                "day": day,
                "theme": f"Ngày {day}: {focus[(day - 1) % len(focus)]}",
                "targetArea": target_region.split(",")[-1],
                "targetRegionKey": target_region,
                "focusTags": list(
                    dict.fromkeys(
                        [
                            focus[(day - 1) % len(focus)],
                            *context["plannerSignals"].get("dominantTags", [])[:2],
                        ]
                    )
                ),
                "pace": intent["pace"],
                "dayPartGoals": {
                    "morning": "Khám phá theo chủ đề.",
                    "lunch": "Ăn trưa linh hoạt.",
                    "afternoon": "Tiếp tục trong cùng khu vực.",
                    "evening": "Giữ lịch linh hoạt.",
                },
                "allocatedSelectedPlaceRefs": allocated_by_day[day],
                "notes": ["Finder sẽ chọn địa điểm và giờ cụ thể."],
            }
            for day in range(1, trip_spec["days"] + 1)
        ]
        return json.dumps(
            {
                "macroPlan": {
                    "title": f"Kế hoạch {intent['destination']}",
                    "destination": intent["destination"],
                    "regionKey": context["regionKey"],
                    "journeyStyle": envelope["researchProposal"][
                        "journeyStyle"
                    ],
                    "journeyPhases": (
                        [
                            {
                                "startDay": 1,
                                "endDay": 3,
                                "baseRegionKey": context["regionKey"],
                                "theme": "Di chuyển và khám phá chặng đầu",
                                "movementGoal": "Phượt có điểm dừng",
                                "stayNights": 2,
                            },
                            {
                                "startDay": 4,
                                "endDay": trip_spec["days"],
                                "baseRegionKey": context["regionKey"],
                                "theme": "Ở lại và khám phá sâu",
                                "movementGoal": "Cân bằng di chuyển với trải nghiệm",
                                "stayNights": trip_spec["days"] - 4,
                            },
                        ]
                        if trip_spec["days"] >= 7
                        else []
                    ),
                    "dayBriefs": day_briefs,
                },
                "unallocatedSelectedPlaces": unallocated,
                "assumptions": ["Generated by test LLM."],
                "warnings": [],
            },
            ensure_ascii=False,
        )


class RecordingPlannerLLM(FakePlannerLLM):
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_payload = ""
        self.calls: list[tuple[str, str]] = []

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        self.system_prompt = system_prompt
        self.user_payload = user_payload
        self.calls.append((system_prompt, user_payload))
        return await super().generate_json(system_prompt, user_payload)


class TripThemeOnlyLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raw = await super().generate_json(system_prompt, user_payload)
        envelope = json.loads(user_payload)
        if envelope["stage"] == "research":
            return raw
        draft = json.loads(raw)
        draft["macroPlan"]["tripThemes"] = [
            {
                "theme": "Lịch sử",
                "focusTags": ["history"],
                "minimumActivities": 1,
                "targetRegionKeys": ["vn,ha-noi"],
            },
            {
                "theme": "Nghệ thuật",
                "focusTags": ["art"],
                "minimumActivities": 1,
                "targetRegionKeys": ["vn,ha-noi"],
            },
        ]
        draft["macroPlan"]["dayBriefs"] = []
        return json.dumps(draft, ensure_ascii=False)


class OverCapacityThemesLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raw = await super().generate_json(system_prompt, user_payload)
        envelope = json.loads(user_payload)
        if envelope["stage"] == "research":
            return raw
        draft = json.loads(raw)
        draft["macroPlan"]["tripThemes"] = [
            {
                "theme": "Ẩm thực địa phương",
                "focusTags": ["food", "restaurant"],
                "minimumActivities": 4,
            },
            {
                "theme": "Văn hóa địa phương",
                "focusTags": ["culture"],
                "minimumActivities": 4,
            },
        ]
        draft["macroPlan"]["dayBriefs"] = []
        return json.dumps(draft, ensure_ascii=False)


class OmittingSelectedPlaceLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raw = await super().generate_json(system_prompt, user_payload)
        envelope = json.loads(user_payload)
        if envelope["stage"] == "research":
            return raw

        draft = json.loads(raw)
        for day in draft["macroPlan"]["dayBriefs"]:
            day["allocatedSelectedPlaceRefs"] = [
                stable_ref
                for stable_ref in day["allocatedSelectedPlaceRefs"]
                if stable_ref != "place-omitted"
            ]
        return json.dumps(draft, ensure_ascii=False)


class HallucinatingSelectedRefLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        raw = await super().generate_json(system_prompt, user_payload)
        if envelope["stage"] == "research":
            return raw

        draft = json.loads(raw)
        draft["macroPlan"]["dayBriefs"][0][
            "allocatedSelectedPlaceRefs"
        ] = ["hallucinated-place"]
        return json.dumps(draft, ensure_ascii=False)


class RepairingPlannerLLM(FakePlannerLLM):
    def __init__(self) -> None:
        self.macro_calls = 0
        self.repair_feedback = ""

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        raw = await super().generate_json(system_prompt, user_payload)
        if envelope["stage"] == "research":
            return raw

        self.macro_calls += 1
        if envelope["stage"] == "macro_plan_repair":
            self.repair_feedback = envelope["validationFeedback"]
            return raw

        draft = json.loads(raw)
        draft["macroPlan"]["dayBriefs"][1]["day"] = 3
        return json.dumps(draft, ensure_ascii=False)


class MultiRepairPlannerLLM(FakePlannerLLM):
    def __init__(self, *, valid_on_macro_call: int) -> None:
        self.valid_on_macro_call = valid_on_macro_call
        self.macro_calls = 0

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        raw = await super().generate_json(system_prompt, user_payload)
        if envelope["stage"] == "research":
            return raw

        self.macro_calls += 1
        if self.macro_calls >= self.valid_on_macro_call:
            return raw

        draft = json.loads(raw)
        draft["macroPlan"]["dayBriefs"][1]["day"] = 3
        return json.dumps(draft, ensure_ascii=False)


class FakeStatisticsProvider:
    def __init__(self, *, place_count: int = 20) -> None:
        self.place_count = place_count
        self.requested_region_keys: list[str] = []

    def get_for_planner(
        self,
        region_key: str,
        *,
        force: bool = False,
    ) -> PlannerRegionStatisticsResult:
        self.requested_region_keys.append(region_key)
        regions = []
        if self.place_count:
            regions = [
                {
                    "regionKey": region_key,
                    "placeCount": self.place_count,
                    "activePlaceCount": self.place_count,
                    "countsByType": {"museum": 4, "restaurant": 8},
                    "tagCounts": {"culture": 4, "food": 8},
                    "timeOfDayCoverage": {
                        "morning": 10,
                        "lunch": 8,
                        "afternoon": 10,
                        "evening": 3,
                        "placesWithKnownHours": 12,
                    },
                    "dataQuality": {
                        "missingOpeningHours": 8,
                        "staleOperationalData": 0,
                    },
                    "areaProfiles": [
                        {
                            "regionKey": "vn,ha-noi,hoan-kiem",
                            "placeCount": 12,
                            "topTags": ["food", "culture"],
                        }
                    ],
                    "plannerSignals": {
                        "dominantTags": ["food", "culture"],
                        "strongDayParts": ["morning", "afternoon"],
                        "weakDayParts": ["evening"],
                        "candidateAreas": [
                            {
                                "regionKey": "vn,ha-noi,hoan-kiem",
                                "placeCount": 12,
                                "topTags": ["food", "culture"],
                            }
                        ],
                    },
                }
            ]
        return PlannerRegionStatisticsResult(
            status="cached",
            region_key=region_key,
            regions=regions,
            snapshot_id="snapshot-3",
            catalog_version=3,
            algorithm_version="auto_statistics_v2_1",
            generated_at="2026-07-28T10:00:00+00:00",
            source_fingerprint="fingerprint",
        )


class FakeExplorerPersistence:
    def load_must_places(
        self,
        intake_id: str,
        user_id: str | None,
    ) -> list[SelectedPlaceCreate]:
        assert intake_id == "intake-tiktok"
        assert user_id is None
        return [
            SelectedPlaceCreate(
                name="Bún chả Hàng Quạt",
                mustVisit=True,
                tags=["food"],
                sourceRefs=[
                    "https://www.tiktok.com/@brandneweats/video/7662905162960243989"
                ],
            )
        ]


def _intent() -> TravelIntent:
    return TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["culture", "food"],
    )
