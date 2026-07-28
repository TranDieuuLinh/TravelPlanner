from __future__ import annotations

import asyncio

from app.integrations.llm.base import LLMClient
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
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.schema import MainPlanCreate, MainPlanFromExplorerCreate
from app.modules.plans.workflows.main_plan_workflow import MainPlanWorkflow


def test_normalize_region_key_from_vietnamese_destination() -> None:
    assert normalize_region_key("Hà Nội") == "vn,ha-noi"
    assert normalize_region_key("ignored", "vn,hai-phong") == "vn,hai-phong"


def test_planner_uses_snapshot_and_accounts_for_selected_places() -> None:
    llm = FakeLLMClient()
    statistics = FakeStatisticsProvider()
    service = PlannerService(llm, statistics)
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
    assert output.macro_plan.day_briefs[0].allocated_selected_place_refs == [
        "place-van-mieu"
    ]
    assert output.unallocated_selected_places[0].place.place_id == (
        "place-excluded"
    )
    assert output.unallocated_selected_places[0].reason_code == (
        "excluded_by_plan_state"
    )
    assert '"regionContext"' in llm.prompts[0]
    assert '"snapshotId":"snapshot-3"' in llm.prompts[0]


def test_planner_marks_day_briefs_not_ready_when_region_is_empty() -> None:
    service = PlannerService(
        FakeLLMClient(),
        FakeStatisticsProvider(place_count=0),
    )

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
    assert output.warnings == ["No Places are available for vn,ha-noi."]


def test_planner_is_ready_with_confirmed_place_when_region_is_empty() -> None:
    service = PlannerService(
        FakeLLMClient(),
        FakeStatisticsProvider(place_count=0),
    )

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
        planner=PlannerService(FakeLLMClient(), statistics),
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
    llm = FakeLLMClient()
    workflow = MainPlanWorkflow(
        explorer=ExplorerService(),
        planner=PlannerService(llm, FakeStatisticsProvider(place_count=0)),
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

    assert plan.status.value == "locked"
    assert plan.days[0].items[0].name == "Văn Miếu"
    assert '"partySize":3' in llm.prompts[0]


class FakeLLMClient(LLMClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate_profile_plan(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "ok"

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        self.prompts.append(user_payload)
        return "{}"


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
