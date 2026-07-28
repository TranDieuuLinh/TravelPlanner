from uuid import uuid4

from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import Plan, TravelIntent, UnscheduledPlace, UserStatus
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    FinderAgentInput,
    PlannerAgentOutput,
    PlanningIntent,
    PlanningMode,
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
    PlanningContextCreate,
    SelectedPlaceCreate,
)
from app.shared.errors import AppError


class MainPlanWorkflow:
    def __init__(
        self,
        explorer: ExplorerService,
        planner: PlannerService,
        finder: FinderService,
        checker: OverallChecker | None = None,
    ) -> None:
        self.explorer = explorer
        self.planner = planner
        self.finder = finder
        self.checker = checker or OverallChecker()

    async def run(self, payload: MainPlanCreate) -> Plan:
        intent = self.explorer.explore(payload)
        return await self._run_planning(
            intent=intent,
            planning_intent=self._planning_intent(intent),
            trip_spec=TripPlanningSpec(days=intent.days),
            explicit_region_key=payload.region_key,
            selected_places=[
                self._selected_place_context(place)
                for place in payload.selected_places
            ],
            user_status=payload.user_status,
        )

    async def run_from_explorer(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> Plan:
        intent = TravelIntent(
            destination=payload.intent.destination,
            days=payload.trip_spec.days,
            budget=payload.intent.budget_level,
            travelStyle=payload.intent.travel_style,
            pace=payload.intent.pace,
            interests=payload.intent.interests,
            mustVisitPlaces=payload.intent.must_visit_places,
            avoidPlaces=payload.intent.avoid_places,
            constraints=payload.intent.constraints,
            clarifyingQuestions=payload.intent.clarifying_questions,
        )
        return await self._run_planning(
            intent=intent,
            planning_intent=payload.intent,
            trip_spec=payload.trip_spec,
            explicit_region_key=payload.region_key,
            selected_places=[
                self._selected_place_context(place)
                for place in payload.selected_places
            ],
            user_status=payload.user_status,
        )

    async def run_from_context(
        self,
        payload: PlanningContextCreate,
    ) -> Plan:
        intent = TravelIntent(
            destination=payload.intent.destination,
            days=payload.trip_spec.days,
            budget=payload.intent.budget_level,
            travelStyle=payload.intent.travel_style,
            pace=payload.intent.pace,
            interests=payload.intent.interests,
            mustVisitPlaces=payload.intent.must_visit_places,
            avoidPlaces=payload.intent.avoid_places,
            constraints=payload.intent.constraints,
            clarifyingQuestions=payload.intent.clarifying_questions,
        )
        return await self._run_planning(
            intent=intent,
            planning_intent=payload.intent,
            trip_spec=payload.trip_spec,
            explicit_region_key=payload.region_key,
            selected_places=[
                self._selected_place_context(place)
                for place in payload.selected_places
            ],
            user_status=payload.user_status,
        )

    async def _run_planning(
        self,
        *,
        intent: TravelIntent,
        planning_intent: PlanningIntent,
        trip_spec: TripPlanningSpec,
        explicit_region_key: str | None,
        selected_places: list[SelectedPlaceContext],
        user_status: UserStatus,
    ) -> Plan:
        region_key = normalize_region_key(intent.destination, explicit_region_key)
        planner_output = await self.planner.create_main_macro_plan(
            intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
        )
        if not planner_output.day_briefs_ready:
            raise AppError(
                422,
                "PLANNER_INPUT_INSUFFICIENT",
                (
                    "Planner cannot create day briefs because the region has no "
                    "catalog Places and no confirmed selected Places."
                ),
                {
                    "selectedPlaces": (
                        "Confirm at least one Place or seed the destination catalog."
                    )
                },
            )

        macro_plan = planner_output.macro_plan
        finder_output = self.finder.fill_agent_plan(
            FinderAgentInput(
                mode=PlanningMode.main,
                intent=planning_intent,
                tripSpec=planner_output.trip_spec,
                macroPlan=macro_plan,
                selectedPlaces=selected_places,
                userStatus=user_status,
            )
        )
        unscheduled_places = self._merge_unscheduled_places(
            planner_output,
            finder_output.unscheduled_places,
        )
        plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.main,
            status=PlanStatus.checking,
            title=macro_plan.title,
            destination=intent.destination,
            intent=intent,
            macroPlan=macro_plan,
            days=finder_output.final_days,
            initialUserStatus=user_status,
            finalUserStatus=finder_output.final_user_status,
            finalPlanStatus=finder_output.final_plan_status,
            unscheduledPlaces=unscheduled_places,
            planningAssumptions=planner_output.assumptions,
            warnings=[
                *planner_output.warnings,
                *finder_output.warnings,
            ],
        )
        check_report = self.checker.check(plan)
        final_status = (
            PlanStatus.locked
            if check_report.status == "passed"
            else PlanStatus.failed
            if check_report.status == "failed"
            else PlanStatus.draft
        )
        return plan.model_copy(
            update={
                "status": final_status,
                "check_report": check_report,
            }
        )

    def _planning_intent(self, intent: TravelIntent) -> PlanningIntent:
        return PlanningIntent(
            destination=intent.destination,
            budgetLevel=intent.budget,
            travelStyle=intent.travel_style,
            pace=intent.pace,
            interests=intent.interests,
            mustVisitPlaces=intent.must_visit_places,
            avoidPlaces=intent.avoid_places,
            constraints=intent.constraints,
            clarifyingQuestions=intent.clarifying_questions,
        )

    def _selected_place_context(
        self,
        place: SelectedPlaceCreate | str,
    ) -> SelectedPlaceContext:
        if isinstance(place, str):
            return SelectedPlaceContext(name=place, mustVisit=True)
        return SelectedPlaceContext.model_validate(place.model_dump())

    def _merge_unscheduled_places(
        self,
        planner_output: PlannerAgentOutput,
        finder_unscheduled: list[UnscheduledPlace],
    ) -> list[UnscheduledPlace]:
        merged = [
            *[
                UnscheduledPlace(
                    placeId=item.place.place_id,
                    name=item.place.name,
                    reasonCode=item.reason_code,
                    reason=item.reason,
                )
                for item in planner_output.unallocated_selected_places
            ],
            *finder_unscheduled,
        ]
        unique: dict[str, UnscheduledPlace] = {}
        for item in merged:
            key = item.place_id or item.name.casefold()
            unique.setdefault(key, item)
        return list(unique.values())
