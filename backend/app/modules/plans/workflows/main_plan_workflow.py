from uuid import uuid4

from app.modules.plans.domain.entities import Plan
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.planner.region_context import normalize_region_key
from app.modules.plans.schema import (
    MainPlanCreate,
    MainPlanFromExplorerCreate,
    SelectedPlaceCreate,
)


class MainPlanWorkflow:
    def __init__(
        self,
        explorer: ExplorerService,
        planner: PlannerService,
        finder: FinderService,
    ) -> None:
        self.explorer = explorer
        self.planner = planner
        self.finder = finder

    async def run(self, payload: MainPlanCreate) -> Plan:
        intent = self.explorer.explore(payload)
        return await self._run(
            payload,
            intent=intent,
            trip_spec=TripPlanningSpec(days=intent.days),
        )

    async def run_from_explorer(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> Plan:
        intent = self.explorer.explore(
            MainPlanCreate(
                destination=payload.intent.destination,
                days=payload.trip_spec.days,
                budget=payload.intent.budget_level,
                travelStyle=payload.intent.travel_style,
                pace=payload.intent.pace,
                interests=payload.intent.interests,
                mustVisitPlaces=payload.intent.must_visit_places,
                avoidPlaces=payload.intent.avoid_places,
                constraints=payload.intent.constraints,
                regionKey=payload.region_key,
                selectedPlaces=payload.selected_places,
                userStatus=payload.user_status,
            )
        )
        main_payload = MainPlanCreate(
            destination=intent.destination,
            days=intent.days,
            budget=intent.budget,
            travelStyle=intent.travel_style,
            pace=intent.pace,
            interests=intent.interests,
            mustVisitPlaces=intent.must_visit_places,
            avoidPlaces=intent.avoid_places,
            constraints=intent.constraints,
            regionKey=payload.region_key,
            selectedPlaces=payload.selected_places,
            userStatus=payload.user_status,
        )
        return await self._run(
            main_payload,
            intent=intent,
            trip_spec=payload.trip_spec,
        )

    async def _run(
        self,
        payload: MainPlanCreate,
        *,
        intent,
        trip_spec: TripPlanningSpec,
    ) -> Plan:
        region_key = normalize_region_key(intent.destination, payload.region_key)
        selected_places = [
            self._selected_place_context(place)
            for place in payload.selected_places
        ]
        planner_output = await self.planner.create_main_macro_plan(
            intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
        )
        macro_plan = planner_output.macro_plan
        finder_result = self.finder.fill_main_plan(
            macro_plan,
            intent,
            selected_places,
            user_status=payload.user_status,
        )
        plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.main,
            status=PlanStatus.locked,
            title=macro_plan.title,
            destination=intent.destination,
            intent=intent,
            macroPlan=macro_plan,
            days=finder_result.days,
            initialUserStatus=payload.user_status,
            finalUserStatus=finder_result.final_user_status,
            finalPlanStatus=finder_result.final_plan_status,
            unscheduledPlaces=finder_result.unscheduled_places,
        )
        return plan

    def _selected_place_context(
        self,
        place: SelectedPlaceCreate | str,
    ) -> SelectedPlaceContext:
        if isinstance(place, str):
            return SelectedPlaceContext(name=place, mustVisit=True)
        return SelectedPlaceContext.model_validate(place.model_dump())
