import time
from uuid import uuid4

from app.modules.planning_runs.repository import PlanningRunRepository
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
from app.modules.preferences.schema import LongTermPreferenceProfile
from app.modules.plans.timing import PlanTimingReport, PlanTimingTrace


class MainPlanWorkflow:
    def __init__(
        self,
        explorer: ExplorerService,
        planner: PlannerService,
        finder: FinderService,
        checker: OverallChecker | None = None,
        planning_runs: PlanningRunRepository | None = None,
    ) -> None:
        self.explorer = explorer
        self.planner = planner
        self.finder = finder
        self.checker = checker or OverallChecker()
        self.planning_runs = planning_runs

    async def run(self, payload: MainPlanCreate) -> Plan:
        intent = self.explorer.explore(payload)
        return await self._run_planning(
            intent=intent,
            planning_intent=self._planning_intent(intent),
            trip_spec=TripPlanningSpec(
                days=intent.days,
                budget={"level": intent.budget},
            ),
            explicit_region_key=payload.region_key,
            selected_places=[
                self._selected_place_context(place)
                for place in payload.selected_places
            ],
            user_status=payload.user_status,
            preference_profile=LongTermPreferenceProfile(),
            allow_finder_suggestions=True,
            source="direct",
        )

    async def run_from_explorer(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> Plan:
        plan, _ = await self.run_from_explorer_with_timing(payload)
        return plan

    async def run_from_explorer_with_timing(
        self,
        payload: MainPlanFromExplorerCreate,
    ) -> tuple[Plan, PlanTimingReport]:
        trace = PlanTimingTrace()
        prepare_started_at = time.perf_counter()
        intent = TravelIntent(
            destination=payload.intent.destination,
            days=payload.trip_spec.days,
            budget=payload.trip_spec.budget.level,
            travelStyle=payload.intent.travel_style,
            pace=payload.intent.pace,
            interests=payload.intent.interests,
            mustVisitPlaces=payload.intent.must_visit_places,
            avoidPlaces=payload.intent.avoid_places,
            constraints=payload.intent.constraints,
            destinationStays=payload.intent.destination_stays,
            constraintPolicy=payload.intent.constraint_policy,
            clarifyingQuestions=payload.intent.clarifying_questions,
        )
        trace.add_stage(
            "preparePlanningContext",
            "Chuẩn bị planning context",
            prepare_started_at,
            details={
                "selectedPlaceCount": len(payload.selected_places),
                "requestedDays": payload.trip_spec.days,
            },
        )
        plan = await self._run_planning(
            intent=intent,
            planning_intent=payload.intent,
            trip_spec=payload.trip_spec,
            explicit_region_key=payload.region_key,
            selected_places=[
                self._selected_place_context(place)
                for place in payload.selected_places
            ],
            user_status=payload.user_status,
            preference_profile=payload.preference_profile,
            allow_finder_suggestions=payload.allow_finder_suggestions,
            timing_trace=trace,
            source="explorer",
            user_id=(
                int(payload.user_id)
                if payload.user_id and payload.user_id.isdigit()
                else None
            ),
            intake_id=payload.intake_id,
        )
        return plan, trace.finish(plan)

    async def run_from_context(
        self,
        payload: PlanningContextCreate,
    ) -> Plan:
        intent = TravelIntent(
            destination=payload.intent.destination,
            days=payload.trip_spec.days,
            budget=payload.trip_spec.budget.level,
            travelStyle=payload.intent.travel_style,
            pace=payload.intent.pace,
            interests=payload.intent.interests,
            mustVisitPlaces=payload.intent.must_visit_places,
            avoidPlaces=payload.intent.avoid_places,
            constraints=payload.intent.constraints,
            destinationStays=payload.intent.destination_stays,
            constraintPolicy=payload.intent.constraint_policy,
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
            preference_profile=LongTermPreferenceProfile(),
            allow_finder_suggestions=True,
            source="context",
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
        preference_profile: LongTermPreferenceProfile,
        allow_finder_suggestions: bool,
        source: str,
        user_id: int | None = None,
        intake_id: str | None = None,
        timing_trace: PlanTimingTrace | None = None,
    ) -> Plan:
        run_id = None
        if self.planning_runs is not None:
            run_id = self.planning_runs.start(
                source=source,
                destination=intent.destination,
                user_id=user_id,
                intake_id=intake_id,
                summary={
                    "days": trip_spec.days,
                    "selectedPlaceCount": len(selected_places),
                    "allowFinderSuggestions": allow_finder_suggestions,
                },
            )
            self.planning_runs.add_stage(
                run_id,
                stage="explorer",
                status="completed",
                input_data={
                    "source": source,
                    "intakeId": intake_id,
                },
                output_data={
                    "intent": planning_intent,
                    "tripSpec": trip_spec,
                    "selectedPlaces": selected_places,
                },
                metadata={"normalizedContext": True},
            )
        try:
            plan = await self._execute_planning(
                intent=intent,
                planning_intent=planning_intent,
                trip_spec=trip_spec,
                explicit_region_key=explicit_region_key,
                selected_places=selected_places,
                user_status=user_status,
                preference_profile=preference_profile,
                allow_finder_suggestions=allow_finder_suggestions,
                run_id=run_id,
                timing_trace=timing_trace,
            )
        except Exception as exc:
            if self.planning_runs is not None and run_id is not None:
                self.planning_runs.add_stage(
                    run_id,
                    stage="workflow",
                    status="failed",
                    error={
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                self.planning_runs.complete(
                    run_id,
                    status="failed",
                    error_code=(
                        exc.code if isinstance(exc, AppError) else type(exc).__name__
                    ),
                    error_message=str(exc),
                )
            raise
        if self.planning_runs is not None and run_id is not None:
            self.planning_runs.complete(
                run_id,
                status="completed",
                summary={
                    "planId": plan.id,
                    "planStatus": plan.status.value,
                    "dayCount": len(plan.days),
                    "unscheduledPlaceCount": len(plan.unscheduled_places),
                    "warningCount": len(plan.warnings),
                },
            )
        return plan

    async def _execute_planning(
        self,
        *,
        intent: TravelIntent,
        planning_intent: PlanningIntent,
        trip_spec: TripPlanningSpec,
        explicit_region_key: str | None,
        selected_places: list[SelectedPlaceContext],
        user_status: UserStatus,
        preference_profile: LongTermPreferenceProfile,
        allow_finder_suggestions: bool,
        run_id: str | None,
        timing_trace: PlanTimingTrace | None,
    ) -> Plan:
        region_key = normalize_region_key(intent.destination, explicit_region_key)
        planner_started = time.perf_counter()
        planner_output = await self.planner.create_main_macro_plan(
            intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            preference_profile=preference_profile,
        )
        if timing_trace is not None:
            timing_trace.add_stage(
                "planner",
                "Planner tạo macro plan",
                planner_started,
                details={
                    "dayBriefCount": len(planner_output.macro_plan.day_briefs),
                    "selectedPlaceCount": len(selected_places),
                },
            )
        if self.planning_runs is not None and run_id is not None:
            self.planning_runs.add_stage(
                run_id,
                stage="planner",
                status=(
                    "completed"
                    if planner_output.day_briefs_ready
                    else "blocked"
                ),
                duration_ms=int((time.perf_counter() - planner_started) * 1_000),
                input_data={
                    "intent": planning_intent,
                    "tripSpec": trip_spec,
                    "regionKey": region_key,
                    "selectedPlaces": selected_places,
                    "preferenceProfile": preference_profile,
                },
                output_data=planner_output,
                metadata={"trace": planner_output.trace},
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
        finder_selected_places = self._filter_finder_selected_places(
            selected_places,
            planner_output,
        )
        finder_input = FinderAgentInput(
            mode=PlanningMode.main,
            intent=planning_intent,
            tripSpec=planner_output.trip_spec,
            macroPlan=macro_plan,
            selectedPlaces=finder_selected_places,
            userStatus=user_status,
            allowFinderSuggestions=allow_finder_suggestions,
            tourismZones=planner_output.tourism_zones,
        )
        finder_started = time.perf_counter()
        finder_output = self.finder.fill_agent_plan(finder_input)
        if timing_trace is not None:
            timing_trace.add_stage(
                "finder",
                "Finder xếp lịch trình và tuyến",
                finder_started,
                details={
                    "scheduledDayCount": len(finder_output.final_days),
                    "finderSelectedPlaceCount": len(finder_selected_places),
                },
            )
        if self.planning_runs is not None and run_id is not None:
            self.planning_runs.add_stage(
                run_id,
                stage="finder",
                status=finder_output.trace.status.value,
                duration_ms=int((time.perf_counter() - finder_started) * 1_000),
                input_data=finder_input,
                output_data=finder_output,
                metadata={"trace": finder_output.trace},
            )
        assemble_started = time.perf_counter()
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
        if timing_trace is not None:
            timing_trace.add_stage(
                "assemblePlan",
                "Dựng plan hoàn chỉnh",
                assemble_started,
                details={
                    "itemCount": sum(len(day.items) for day in plan.days),
                    "unscheduledCount": len(unscheduled_places),
                },
            )
        checker_started = time.perf_counter()
        check_report = self.checker.check(plan)
        if timing_trace is not None:
            timing_trace.add_stage(
                "checkOverall",
                "Kiểm tra tính khả thi",
                checker_started,
                details={
                    "status": check_report.status,
                    "issueCount": len(check_report.issues),
                },
            )
        if self.planning_runs is not None and run_id is not None:
            self.planning_runs.add_stage(
                run_id,
                stage="checker",
                status=check_report.status,
                duration_ms=int((time.perf_counter() - checker_started) * 1_000),
                input_data={
                    "planId": plan.id,
                    "dayCount": len(plan.days),
                    "unscheduledPlaces": plan.unscheduled_places,
                },
                output_data=check_report,
            )
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
            travelStyle=intent.travel_style,
            pace=intent.pace,
            interests=intent.interests,
            mustVisitPlaces=intent.must_visit_places,
            avoidPlaces=intent.avoid_places,
            constraints=intent.constraints,
            destinationStays=intent.destination_stays,
            constraintPolicy=intent.constraint_policy,
            clarifyingQuestions=intent.clarifying_questions,
        )

    def _selected_place_context(
        self,
        place: SelectedPlaceCreate | str,
    ) -> SelectedPlaceContext:
        if isinstance(place, str):
            return SelectedPlaceContext(name=place, mustVisit=True)
        return SelectedPlaceContext.model_validate(place.model_dump())

    def _filter_finder_selected_places(
        self,
        selected_places: list[SelectedPlaceContext],
        planner_output: PlannerAgentOutput,
    ) -> list[SelectedPlaceContext]:
        unallocated_refs = {
            item.place.stable_ref
            for item in planner_output.unallocated_selected_places
        }
        if not unallocated_refs:
            return selected_places
        return [
            place
            for place in selected_places
            if place.stable_ref not in unallocated_refs
        ]

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
