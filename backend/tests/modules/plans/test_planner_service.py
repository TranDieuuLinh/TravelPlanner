from __future__ import annotations

import asyncio

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
from app.modules.plans.planner.region_context import normalize_region_key
from app.modules.plans.checks.backup_validator import BackupValidator
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.schema import (
    BackupPlanCreate,
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    PlanningContextCreate,
)
from app.modules.plans.workflows.backup_plan_workflow import BackupPlanWorkflow
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow
from app.shared.errors import AppError


def test_normalize_region_key_from_vietnamese_destination() -> None:
    assert normalize_region_key("Hà Nội") == "vn,ha-noi"
    assert normalize_region_key("ignored", "vn,hai-phong") == "vn,hai-phong"


def test_planner_uses_snapshot_and_accounts_for_selected_places() -> None:
    statistics = FakeStatisticsProvider()
    service = PlannerService(statistics)
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
    assert output.trace.notes == ["snapshotId=snapshot-3"]
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
    assert output.assumptions[0].startswith(
        "Planner used deterministic rules"
    )


def test_planner_marks_day_briefs_not_ready_when_region_is_empty() -> None:
    service = PlannerService(FakeStatisticsProvider(place_count=0))

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
        "No catalog Places are available for vn,ha-noi; "
        "Finder is limited to confirmed selected Places."
    ]


def test_planner_can_continue_without_catalog_when_places_are_confirmed() -> None:
    service = PlannerService(FakeStatisticsProvider(place_count=0))

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
    service = PlannerService(FakeStatisticsProvider())
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
    assert allocated == 6
    assert output.unallocated_selected_places[0].place.place_id == "place-7"
    assert output.unallocated_selected_places[0].reason_code == "no_day_capacity"


def test_planner_does_not_allocate_explicitly_avoided_place() -> None:
    service = PlannerService(FakeStatisticsProvider())
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


def test_planner_is_ready_with_confirmed_place_when_region_is_empty() -> None:
    service = PlannerService(FakeStatisticsProvider(place_count=0))

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


def test_main_workflow_accepts_structured_selected_places() -> None:
    statistics = FakeStatisticsProvider()
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=PlannerService(statistics),
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
        planner=PlannerService(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
    )
    payload = MainPlanFromExplorerCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "budgetLevel": "medium",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture"],
            },
            "tripSpec": {
                "days": 2,
                "partySize": 3,
                "budget": {
                    "inputMode": "unknown",
                    "currency": "VND",
                    "isHardCap": False,
                    "confidence": "low",
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


def test_main_workflow_accepts_planning_context() -> None:
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=PlannerService(FakeStatisticsProvider(place_count=0)),
        finder=FinderService(),
        checker=OverallChecker(),
    )
    payload = PlanningContextCreate.model_validate(
        {
            "intent": {
                "destination": "Hà Nội",
                "budgetLevel": "medium",
                "travelStyle": "local",
                "pace": "balanced",
                "interests": ["culture"],
            },
            "tripSpec": {
                "days": 2,
                "partySize": 2,
                "budget": {
                    "inputMode": "unknown",
                    "currency": "VND",
                    "isHardCap": False,
                    "confidence": "low",
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
        planner=PlannerService(FakeStatisticsProvider()),
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
        planner=PlannerService(FakeStatisticsProvider(place_count=0)),
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
    planner = PlannerService(statistics)
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
    planner = PlannerService(statistics)
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


def _intent() -> TravelIntent:
    return TravelIntent(
        destination="Hà Nội",
        days=2,
        budget=BudgetLevel.medium,
        travelStyle="local",
        pace=TravelPace.balanced,
        interests=["culture", "food"],
    )
