from uuid import uuid4

from app.modules.plans.domain.entities import Plan
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
        return await self._run_planning(
            intent=intent,
            planning_intent=self._planning_intent(intent),
            trip_spec=TripPlanningSpec(days=intent.days),
            explicit_region_key=payload.region_key,
            selected_places=selected_places,
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
        region_key = normalize_region_key(
            intent.destination,
            explicit_region_key,
        )
        planner_output = await self.planner.create_main_macro_plan(
            intent,
            trip_spec=trip_spec,
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
        selected_place_names = [place.name for place in finder_places]
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
            travelStyle=intent.travel_style,https://github.com/TranDieuuLinh/VSF_TravelPlanner/pull/16/conflict?name=backend%252Fapp%252Fmodules%252Fplans%252Fworkflows%252Fmain_plan_workflow.py&ancestor_oid=52f76b9dfd8961638c99953e6140d20984437587&base_oid=6081b1ae837f0b8d0038f1100a1524b7835764a6&head_oid=2e3be01fb60d8655510a36e507d0bbb9dda5be3d
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
