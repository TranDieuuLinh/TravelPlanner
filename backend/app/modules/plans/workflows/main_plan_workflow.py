from uuid import uuid4

from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import Plan, TravelIntent
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.finder.finder_service import FinderService
from app.modules.plans.planner.planner_service import PlannerService
from app.modules.plans.planner.region_context import normalize_region_key
from app.modules.plans.schema import MainPlanCreate, SelectedPlaceCreate


class MainPlanWorkflow:
    def __init__(
        self,
        explorer: ExplorerService,
        planner: PlannerService,
        finder: FinderService,
        checker: OverallChecker,
    ) -> None:
        self.explorer = explorer
        self.planner = planner
        self.finder = finder
        self.checker = checker

    async def run(self, payload: MainPlanCreate) -> Plan:
        intent = self.explorer.explore(payload)
        region_key = normalize_region_key(intent.destination, payload.region_key)
        selected_places = [
            self._selected_place_context(place)
            for place in payload.selected_places
        ]
        return await self._build_plan(
            intent,
            trip_spec=TripPlanningSpec(days=intent.days),
            region_key=region_key,
            planner_places=selected_places,
            finder_places=selected_places,
        )

    async def _build_plan(
        self,
        intent: TravelIntent,
        *,
        trip_spec: TripPlanningSpec,
        region_key: str,
        planner_places: list[SelectedPlaceContext],
        finder_places: list[SelectedPlaceContext],
    ) -> Plan:
        planner_output = await self.planner.create_main_macro_plan(
            intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=planner_places,
        )
        macro_plan = planner_output.macro_plan
        selected_place_names = [place.name for place in finder_places]
        days = self.finder.fill_main_plan(
        finder_result = self.finder.fill_main_plan(
            macro_plan,
            intent,
            selected_places,
            user_status=payload.user_status,
        )
        plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.main,
            status=PlanStatus.checking,
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
        check_report = self.checker.check(plan)
        return plan.model_copy(update={"status": PlanStatus.locked, "check_report": check_report})

    def _selected_place_context(
        self,
        place: SelectedPlaceCreate | str,
    ) -> SelectedPlaceContext:
        if isinstance(place, str):
            return SelectedPlaceContext(name=place, mustVisit=True)
        return SelectedPlaceContext.model_validate(place.model_dump())
