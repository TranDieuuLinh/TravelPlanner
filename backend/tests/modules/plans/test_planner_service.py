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
    TripThemeDraft,
    TripPlanningSpec,
)
from app.modules.plans.trip_theme_planner.service import TripThemePlannerService
from app.modules.plans.trip_theme_planner.region_context import (
    canonical_destination_name,
    normalize_region_key,
    normalize_search_region_key,
)
from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.schema import (
    BackupPlanCreate,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanningContextCreate,
    SelectedPlaceCreate,
)
from app.modules.plans.repository import PlanRepository
from app.modules.plans.service import (
    PlanService,
    _ensure_url_place_coverage,
    _merge_selected_places,
)
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.shared.errors import AppError


def test_needs_review_url_candidate_is_preserved_as_unscheduled_place() -> None:
    review = PlaceCandidateReview.model_validate(
        {
            "candidateId": "candidate-egg-coffee",
            "name": "Egg coffee near the old quarter",
            "category": "cafe",
            "status": "needs_review",
            "provider": "google_maps_scraper",
            "sourceUrls": ["https://example.com/hanoi-video"],
            "sourceDay": 1,
            "sourceActivity": "Try egg coffee",
            "topMatches": [
                {
                    "rank": 1,
                    "matchSource": "external_provider",
                    "provider": "google_maps_scraper",
                    "placeId": "cafe-a",
                    "name": "Cafe A",
                    "score": 0.78,
                }
            ],
        }
    )

    unscheduled = MainPlanWorkflow._needs_review_unscheduled([review])

    assert len(unscheduled) == 1
    item = unscheduled[0]
    assert item.place_id is None
    assert item.candidate_id == "candidate-egg-coffee"
    assert item.name == "Egg coffee near the old quarter"
    assert item.reason_code == "identity_needs_review"
    assert item.source_refs == ["https://example.com/hanoi-video"]
    assert item.top_matches[0]["placeId"] == "cafe-a"


def test_needs_review_without_matches_is_still_preserved_as_unscheduled() -> None:
    review = PlaceCandidateReview.model_validate(
        {
            "candidateId": "candidate-unknown",
            "name": "Unknown place from video",
            "category": "other",
            "status": "needs_review",
            "sourceUrls": ["https://example.com/video"],
            "topMatches": [],
        }
    )

    unscheduled = MainPlanWorkflow._needs_review_unscheduled([review])

    assert len(unscheduled) == 1
    assert unscheduled[0].candidate_id == "candidate-unknown"
    assert unscheduled[0].reason_code == "identity_needs_review"
    assert unscheduled[0].top_matches == []


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
    ("destination", "expected"),
    [
        ("Hanoi", "Hà Nội"),
        ("Hanoi, Vietnam", "Hà Nội"),
        ("Saigon", "TP. Hồ Chí Minh"),
        ("Danang", "Đà Nẵng"),
        ("Paris", "Paris"),
    ],
)
def test_canonical_destination_name_prefers_vietnamese_display_name(
    destination: str,
    expected: str,
) -> None:
    assert canonical_destination_name(destination) == expected


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
        trip_theme_planner=_planner(statistics),
        place_selector=PlaceSelectorService(),
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
    assert plan.trip_themes
    assert len(plan.days) == 1


def test_main_workflow_reuses_theme_but_reruns_downstream_planning() -> None:
    statistics = FakeStatisticsProvider()
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(statistics),
        place_selector=PlaceSelectorService(),
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture"],
            },
            "tripSpec": {"days": 1},
            "selectedPlaces": [],
        }
    )
    first = asyncio.run(workflow.run_from_explorer(payload))
    statistics.requested_region_keys.clear()

    second, timing = asyncio.run(
        workflow.run_from_explorer_with_timing(
            payload,
            reuse_theme_plan=first,
        )
    )

    assert statistics.requested_region_keys == []
    assert second.trip_themes == first.trip_themes
    theme_stage = next(stage for stage in timing.stages if stage.key == "tripThemePlanner")
    assert theme_stage.details["reused"] is True
    assert theme_stage.sub_stages == []
    assert any(stage.key == "placeSelector" for stage in timing.stages)


def test_city_stay_spans_two_days_without_becoming_place() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
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
                        "sourceRefs": ["https://www.instagram.com/reel/example"],
                    }
                ],
            },
            "tripSpec": {"days": 2},
            "selectedPlaces": [],
            "allowPlaceSuggestions": False,
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    assert len(plan.days) == 2
    assert all(
        [item.role for item in day.items]
        == ["breakfast_meal", "lunch_meal", "dinner_meal"]
        for day in plan.days
    )
    assert all(day.theme is None for day in plan.days)
    assert all(
        "theme" not in day.model_dump(mode="json", by_alias=True)
        for day in plan.days
    )


def test_trip_theme_planner_uses_snapshot_and_returns_only_themes() -> None:
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
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=selected_places,
            plan_state=PlanWorkingState(excludedPlaceNames=["Bỏ qua"]),
        )
    )

    assert statistics.requested_region_keys == ["vn,ha-noi"]
    assert output.trip_themes_ready is True
    serialized = output.model_dump(mode="json", by_alias=True)
    assert "macroPlan" not in serialized
    assert "dayBriefs" not in serialized
    assert serialized["tripThemes"]
    assert "generator=llm" in output.trace.notes
    assert not any(
        note.startswith("researchPromptVersion=") for note in output.trace.notes
    )
    assert (
        "promptVersion=trip_theme_planner_graph_v6_structured_output"
        in output.trace.notes
    )
    assert "snapshotId=snapshot-3" in output.trace.notes
    assert output.assumptions == ["Generated by test LLM."]


def test_url_itinerary_uses_duration_capacity_and_keeps_source_order() -> None:
    statistics = FakeStatisticsProvider(place_count=0)
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(statistics),
        place_selector=PlaceSelectorService(),
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
        place.name for place in source_places
    ]
    assert plan.unscheduled_places == []
    assert [item.source_order for item in plan.days[0].items] == list(range(1, 8))
    assert plan.days[0].items[0].place_id is None
    assert plan.days[0].items[0].notes == (
        "Đã định vị theo địa chỉ; chưa xác minh POI cụ thể."
    )
    assert plan.days[0].items[1].notes == "Order an egg coffee."
    assert len(plan.days[0].transport_legs) == 6


@pytest.mark.parametrize(("stop_count", "requested_days"), [(10, 4), (20, 6)])
def test_url_itinerary_without_source_days_fills_every_stop(
    stop_count: int,
    requested_days: int,
) -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider(place_count=0)),
        place_selector=PlaceSelectorService(),
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
                place.model_dump(mode="json", by_alias=True) for place in places
            ],
            "allowPlaceSuggestions": False,
        }
    )

    plan = asyncio.run(workflow.run_from_explorer(payload))

    scheduled = [
        item
        for day in plan.days
        for item in day.items
        if item.source == "selected_place"
    ]
    assert {item.name for item in scheduled} == {place.name for place in places}
    assert plan.unscheduled_places == []


def test_trip_theme_planner_marks_themes_not_ready_when_region_is_empty() -> None:
    service = _planner(FakeStatisticsProvider(place_count=0))

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.trip_themes_ready is False
    assert output.trace.status.value == "blocked"
    assert output.warnings == [
        "Không có Place active cho vn,ha-noi; PlaceSelector chỉ có thể dùng các "
        "địa điểm người dùng đã chọn."
    ]


def test_trip_theme_planner_skips_statistics_when_intent_is_explicit() -> None:
    statistics = FakeStatisticsProvider()
    service = TripThemePlannerService(
        statistics,
        FakePlannerLLM(),
        skip_statistics_for_explicit_intent=True,
    )

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.trip_themes_ready is True
    assert statistics.requested_region_keys == []
    assert "statisticsStatus=skipped_explicit_intent" in output.trace.notes


def test_planner_sends_small_area_statistics_to_llm() -> None:
    llm = RecordingPlannerLLM()
    service = TripThemePlannerService(FakeStatisticsProvider(), llm)

    asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert len(llm.calls) == 1
    assert "Bạn là Trip Theme Planner" in llm.system_prompt
    assert "knowledge_entities" in llm.system_prompt
    assert "source_backed" in llm.system_prompt
    assert "dataset reference" in llm.system_prompt
    payload = json.loads(llm.user_payload)
    assert payload["stage"] == "trip_theme_plan"
    assert payload["promptVersion"] == (
        "trip_theme_planner_graph_v6_structured_output"
    )
    assert "requiredOutputShape" not in payload
    assert llm.response_schemas == [TripThemeDraft.model_json_schema()]
    assert (
        payload["plannerInput"]["regionContext"]["plannerSignals"]["candidateAreas"][0][
            "regionKey"
        ]
        == "vn,ha-noi,hoan-kiem"
    )
    assert payload["themeSelectionPolicy"]["selectionMode"] == ("current_trip_intent")
    assert "researchProposal" not in payload
    assert "verifiedResearch" not in payload


def test_trip_theme_planner_returns_requirements_without_route_buckets() -> None:
    service = TripThemePlannerService(FakeStatisticsProvider(), TripThemeOnlyLLM())

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert [theme.theme for theme in output.trip_themes] == [
        "Lịch sử",
        "Nghệ thuật",
    ]
    assert "selectionDays" not in output.model_dump(mode="json", by_alias=True)


def test_planner_normalizes_food_themes_and_over_capacity_requirements() -> None:
    service = TripThemePlannerService(
        FakeStatisticsProvider(),
        OverCapacityThemesLLM(),
    )

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert [theme.theme for theme in output.trip_themes] == ["Văn hóa địa phương"]
    assert output.trip_themes[0].minimum_activities == 4
    assert any("khung bữa ăn riêng" in warning for warning in output.warnings)


def test_planner_can_continue_without_catalog_when_places_are_confirmed() -> None:
    service = _planner(FakeStatisticsProvider(place_count=0))

    output = asyncio.run(
        service.create_trip_themes(
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

    assert output.trip_themes_ready is True
    assert output.trip_themes


def test_place_selector_reports_confirmed_places_over_day_capacity() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
    )
    selected_places = [
        SelectedPlaceContext(
            placeId=f"place-{index}",
            name=f"Place {index}",
            mustVisit=True,
        )
        for index in range(1, 8)
    ]

    plan = asyncio.run(
        workflow.run_from_explorer(
            MainPlanFromExplorerCreate.model_validate(
                {
                    "intent": _intent().model_dump(mode="json", by_alias=True),
                    "tripSpec": {"days": 2},
                    "selectedPlaces": [
                        place.model_dump(mode="json", by_alias=True)
                        for place in selected_places
                    ],
                }
            )
        )
    )

    allocated = sum(
        item.source == "selected_place" for day in plan.days for item in day.items
    )
    assert allocated == 6
    assert len(plan.unscheduled_places) == 1
    assert all(
        item.reason_code in {"no_available_slot", "insufficient_time"}
        for item in plan.unscheduled_places
    )


def test_place_selector_does_not_allocate_explicitly_avoided_place() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
    )
    intent = _intent().model_copy(update={"avoid_places": ["Avoid Me"]})

    plan = asyncio.run(
        workflow.run_from_explorer(
            MainPlanFromExplorerCreate.model_validate(
                {
                    "intent": intent.model_dump(mode="json", by_alias=True),
                    "tripSpec": {"days": 1},
                    "selectedPlaces": [
                        {
                            "placeId": "avoid-me",
                            "name": "Avoid Me",
                            "mustVisit": True,
                        }
                    ],
                }
            )
        )
    )

    assert all(item.place_id != "avoid-me" for item in plan.days[0].items)
    assert plan.unscheduled_places[0].place_id == "avoid-me"
    assert plan.unscheduled_places[0].reason_code == "avoided_by_user"


def test_trip_theme_planner_does_not_let_llm_allocate_selected_places() -> None:
    service = TripThemePlannerService(
        FakeStatisticsProvider(),
        OmittingSelectedPlaceLLM(),
    )

    output = asyncio.run(
        service.create_trip_themes(
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

    assert output.trip_themes_ready is True
    assert "selectionDays" not in output.model_dump(mode="json", by_alias=True)


def test_trip_theme_planner_ignores_hallucinated_day_allocation() -> None:
    llm = HallucinatingSelectedRefLLM()
    service = TripThemePlannerService(FakeStatisticsProvider(), llm)

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=1),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.trip_themes_ready is True
    assert "selectionDays" not in output.model_dump(mode="json", by_alias=True)
    assert "repairAttempts=0" in output.trace.notes


def test_trip_theme_planner_repairs_invalid_theme_contract_once() -> None:
    llm = RepairingPlannerLLM()
    service = TripThemePlannerService(FakeStatisticsProvider(), llm)
    timing_stages = []

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
            on_timing_stage=timing_stages.append,
        )
    )

    assert output.trip_themes_ready is True
    assert llm.macro_calls == 2
    assert "tripThemes.0.minimumActivities" in llm.repair_feedback
    assert [stage.key for stage in timing_stages] == [
        "regionStatistics",
        "llmGenerate",
        "validateThemeDraft",
        "llmRepair1",
        "validateThemeRepair1",
    ]
    assert timing_stages[2].details["status"] == "failed"
    assert timing_stages[-1].details["status"] == "completed"
    assert llm.response_schemas == [
        TripThemeDraft.model_json_schema(),
        TripThemeDraft.model_json_schema(),
    ]


def test_trip_theme_planner_can_repair_invalid_contract_three_times() -> None:
    llm = MultiRepairPlannerLLM(valid_on_macro_call=4)
    service = TripThemePlannerService(FakeStatisticsProvider(), llm)

    output = asyncio.run(
        service.create_trip_themes(
            _intent(),
            trip_spec=TripPlanningSpec(days=2),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    assert output.trip_themes_ready is True
    assert llm.macro_calls == 4
    assert "repairAttempts=3" in output.trace.notes


def test_trip_theme_planner_stops_after_three_failed_repairs() -> None:
    llm = MultiRepairPlannerLLM(valid_on_macro_call=5)
    service = TripThemePlannerService(FakeStatisticsProvider(), llm)

    with pytest.raises(
        RuntimeError,
        match="after 3 repair attempts",
    ):
        asyncio.run(
            service.create_trip_themes(
                _intent(),
                trip_spec=TripPlanningSpec(days=2),
                region_key="vn,ha-noi",
                selected_places=[],
            )
        )

    assert llm.macro_calls == 4


def test_trip_theme_planner_is_ready_with_confirmed_place_without_catalog() -> None:
    service = _planner(FakeStatisticsProvider(place_count=0))

    output = asyncio.run(
        service.create_trip_themes(
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

    assert output.trip_themes_ready is True
    assert output.trace.status.value == "completed"


def test_long_trip_still_returns_only_trip_wide_themes() -> None:
    service = _planner(FakeStatisticsProvider())

    output = asyncio.run(
        service.create_trip_themes(
            _intent().model_copy(update={"days": 7, "travel_style": "phượt"}),
            trip_spec=TripPlanningSpec(days=7),
            region_key="vn,ha-noi",
            selected_places=[],
        )
    )

    serialized = output.model_dump(mode="json", by_alias=True)
    assert output.trip_spec.days == 7
    assert output.trip_themes
    assert "journeyPhases" not in serialized
    assert "selectionDays" not in serialized


def test_main_workflow_accepts_structured_selected_places() -> None:
    statistics = FakeStatisticsProvider()
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(statistics),
        place_selector=PlaceSelectorService(),
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

    assert plan.trip_themes
    assert "macroPlan" not in plan.model_dump(mode="json", by_alias=True)
    assert plan.days[0].items[0].name == "Văn Miếu"


def test_main_workflow_accepts_confirmed_explorer_context() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider(place_count=0)),
        place_selector=PlaceSelectorService(),
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

    assert plan.status.value == "failed"
    assert plan.check_report is not None
    assert plan.check_report.status == "failed"
    assert any(
        issue.code == "daily_meal_structure_invalid"
        for issue in plan.check_report.issues
    )
    assert plan.days[0].items[0].name == "Văn Miếu"


def test_plan_service_uses_persisted_explorer_places_from_intake() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider(place_count=0)),
        place_selector=PlaceSelectorService(),
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
        "capacityPreflight",
        "preparePlanningContext",
        "tripThemePlanner",
        "placeSelector",
        "assemblePlan",
        "checkOverall",
    ]
    theme_stage = next(
        stage for stage in timing.stages if stage.key == "tripThemePlanner"
    )
    assert [stage.key for stage in theme_stage.sub_stages] == [
        "regionStatistics",
        "llmGenerate",
        "validateThemeDraft",
    ]
    assert timing.day_count == len(plan.days)
    assert timing.item_count == sum(len(day.items) for day in plan.days)


def test_plan_service_expands_days_to_fit_merged_selected_places() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
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

    assert plan.intent.days == 2
    assert len(plan.days) == 2


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
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
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

    assert plan.intent.days == 2
    assert len(plan.days) == 2
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
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
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
    assert plan.unscheduled_places == []
    represented_names = {item.name for day in plan.days for item in day.items} | {
        item.name for item in plan.unscheduled_places
    }
    assert represented_names == {f"TikTok Place {index}" for index in range(1, 5)}


def test_url_coverage_guard_retains_a_place_omitted_by_downstream_planner() -> None:
    source_url = "https://www.youtube.com/watch?v=coverage"
    selected = SelectedPlaceCreate(
        placeId="url-place",
        name="URL Place",
        address="Hà Nội",
        latitude=21.03,
        longitude=105.84,
        sourceRefs=[source_url],
        sourceProvider="database",
        sourceActivity="Visit the source place",
    )
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
    )
    plan = asyncio.run(
        workflow.run_from_explorer(
            MainPlanFromExplorerCreate.model_validate(
                {
                    "intent": {"destination": "Hà Nội", "pace": "balanced"},
                    "tripSpec": {"days": 1},
                    "selectedPlaces": [selected.model_dump(mode="json", by_alias=True)],
                    "allowPlaceSuggestions": False,
                }
            )
        )
    )
    damaged = plan.model_copy(
        update={
            "days": [day.model_copy(update={"items": []}) for day in plan.days],
            "unscheduled_places": [],
        }
    )

    repaired = _ensure_url_place_coverage(damaged, [selected])

    assert len(repaired.unscheduled_places) == 1
    retained = repaired.unscheduled_places[0]
    assert retained.place_id == "url-place"
    assert retained.reason_code == "planner_omitted_selected_place"
    assert retained.source_refs == [source_url]
    assert retained.source_activity == "Visit the source place"


def test_food_url_places_use_meal_slots_before_expanding_days() -> None:
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
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
        trip_theme_planner=_planner(FakeStatisticsProvider(place_count=0)),
        place_selector=PlaceSelectorService(),
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
    assert {item.place_id for day in plan.days for item in day.items} >= {
        "place-van-mieu",
        "place-ho-guom",
    }
    assert plan.status.value == "failed"
    assert plan.check_report is not None
    assert any(
        issue.code == "daily_meal_structure_invalid"
        for issue in plan.check_report.issues
    )
    assert plan.check_report.status == "failed"


def test_main_workflow_keeps_overflow_visible_when_daily_structure_fails() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider()),
        place_selector=PlaceSelectorService(),
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

    assert plan.status.value == "failed"
    assert plan.check_report is not None
    assert plan.check_report.status == "failed"
    assert {item.place_id for item in plan.unscheduled_places} == {"place-4"}
    assert all(
        item.reason_code in {"no_available_slot", "insufficient_time"}
        for item in plan.unscheduled_places
    )


def test_main_workflow_rejects_empty_catalog_and_no_confirmed_places() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=_planner(FakeStatisticsProvider(place_count=0)),
        place_selector=PlaceSelectorService(),
        checker=OverallChecker(),
    )
    payload = MainPlanCreate(
        destination="Hà Nội",
        days=1,
        selectedPlaces=[],
    )

    with pytest.raises(AppError) as captured:
        asyncio.run(workflow.run(payload))

    assert captured.value.code == "TRIP_THEME_INPUT_INSUFFICIENT"
    assert captured.value.status_code == 422


def test_backup_preserves_optional_confirmed_place() -> None:
    statistics = FakeStatisticsProvider()
    planner = _planner(statistics)
    finder = PlaceSelectorService()
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=planner,
        place_selector=finder,
        checker=OverallChecker(),
    )
    backup_workflow = BackupPlanWorkflow(
        place_selector=finder,
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
    finder = PlaceSelectorService()
    main_workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        trip_theme_planner=planner,
        place_selector=finder,
        checker=OverallChecker(),
    )
    backup_workflow = BackupPlanWorkflow(
        place_selector=finder,
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
        item.name != "Coastal Stop" for day in backup_plan.days for item in day.items
    )
    assert "avoid_outdoor" in backup_plan.intent.constraints


def _planner(statistics: "FakeStatisticsProvider") -> TripThemePlannerService:
    return TripThemePlannerService(statistics, FakePlannerLLM())


class FakePlannerLLM:
    def __init__(self) -> None:
        self.response_schemas: list[dict] = []

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        self.response_schemas.append(response_schema)
        return await self.generate_json(system_prompt, user_payload)

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
                        "road_trip" if trip_spec["days"] >= 7 else "local_base"
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

        focus = intent["interests"] or ["culture"]
        return json.dumps(
            {
                "tripThemes": [
                    {
                        "theme": f"Trải nghiệm {value}",
                        "focusTags": [value],
                        "minimumActivities": 1,
                        "targetRegionKeys": [context["regionKey"]],
                    }
                    for value in focus[:4]
                ],
                "assumptions": ["Generated by test LLM."],
                "warnings": [],
            },
            ensure_ascii=False,
        )


class RecordingPlannerLLM(FakePlannerLLM):
    def __init__(self) -> None:
        super().__init__()
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
        draft["tripThemes"] = [
            {
                "theme": "Lịch sử",
                "focusTags": ["history"],
                "minimumActivities": 1,
                "targetRegionKeys": ["vn,ha-noi,hoan-kiem"],
            },
            {
                "theme": "Nghệ thuật",
                "focusTags": ["art"],
                "minimumActivities": 1,
                "targetRegionKeys": ["vn,ha-noi"],
            },
        ]
        return json.dumps(draft, ensure_ascii=False)


class OverCapacityThemesLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raw = await super().generate_json(system_prompt, user_payload)
        envelope = json.loads(user_payload)
        if envelope["stage"] == "research":
            return raw
        draft = json.loads(raw)
        draft["tripThemes"] = [
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
        return json.dumps(draft, ensure_ascii=False)


class OmittingSelectedPlaceLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        raw = await super().generate_json(system_prompt, user_payload)
        envelope = json.loads(user_payload)
        if envelope["stage"] == "research":
            return raw

        return raw


class HallucinatingSelectedRefLLM(FakePlannerLLM):
    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        raw = await super().generate_json(system_prompt, user_payload)
        if envelope["stage"] == "research":
            return raw

        draft = json.loads(raw)
        draft["selectionDays"] = [
            {"day": 99, "allocatedSelectedPlaceRefs": ["hallucinated-place"]}
        ]
        return json.dumps(draft, ensure_ascii=False)


class RepairingPlannerLLM(FakePlannerLLM):
    def __init__(self) -> None:
        super().__init__()
        self.macro_calls = 0
        self.repair_feedback = ""

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        envelope = json.loads(user_payload)
        raw = await super().generate_json(system_prompt, user_payload)
        if envelope["stage"] == "research":
            return raw

        self.macro_calls += 1
        if envelope["stage"] == "trip_theme_plan_repair":
            self.repair_feedback = envelope["validationFeedback"]
            return raw

        draft = json.loads(raw)
        draft["tripThemes"][0]["minimumActivities"] = 0
        return json.dumps(draft, ensure_ascii=False)


class MultiRepairPlannerLLM(FakePlannerLLM):
    def __init__(self, *, valid_on_macro_call: int) -> None:
        super().__init__()
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
        draft["tripThemes"][0]["minimumActivities"] = 0
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
