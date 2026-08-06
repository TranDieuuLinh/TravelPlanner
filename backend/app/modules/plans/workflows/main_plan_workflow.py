import time
from typing import Callable
from uuid import uuid4

from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import (
    Plan,
    TravelIntent,
    UnscheduledPlace,
    UserStatus,
)
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    PlaceSelectionInput,
    TripThemePlanningOutput,
    PlanningIntent,
    PlanningMode,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.place_selector.activity_fallback import (
    RouteAwareActivityFallback,
)
from app.modules.plans.trip_theme_planner.service import TripThemePlannerService
from app.modules.plans.trip_theme_planner.region_context import normalize_region_key
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
        trip_theme_planner: TripThemePlannerService,
        place_selector: PlaceSelectorService,
        checker: OverallChecker | None = None,
        planning_runs: PlanningRunRepository | None = None,
    ) -> None:
        self.explorer = explorer
        self.trip_theme_planner = trip_theme_planner
        self.place_selector = place_selector
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
                self._selected_place_context(place) for place in payload.selected_places
            ],
            user_status=payload.user_status,
            preference_profile=LongTermPreferenceProfile(),
            allow_finder_gap_fill=True,
            allow_replace_source_places=False,
            source="direct",
            candidate_reviews=[],
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
        *,
        on_timing_update: Callable[[PlanTimingReport], None] | None = None,
    ) -> tuple[Plan, PlanTimingReport]:
        trace = PlanTimingTrace(on_update=on_timing_update)
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
                "dataSource": "Explorer snapshot",
            },
        )
        plan = await self._run_planning(
            intent=intent,
            planning_intent=payload.intent,
            trip_spec=payload.trip_spec,
            explicit_region_key=payload.region_key,
            selected_places=[
                self._selected_place_context(place) for place in payload.selected_places
            ],
            user_status=payload.user_status,
            preference_profile=payload.preference_profile,
            allow_finder_gap_fill=payload.allow_finder_gap_fill,
            allow_replace_source_places=payload.allow_replace_source_places,
            timing_trace=trace,
            source="explorer",
            candidate_reviews=payload.candidate_reviews,
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
                self._selected_place_context(place) for place in payload.selected_places
            ],
            user_status=payload.user_status,
            preference_profile=LongTermPreferenceProfile(),
            allow_finder_gap_fill=True,
            allow_replace_source_places=False,
            source="context",
            candidate_reviews=[],
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
        allow_finder_gap_fill: bool,
        allow_replace_source_places: bool,
        source: str,
        candidate_reviews: list[PlaceCandidateReview],
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
                    "allowFinderGapFill": allow_finder_gap_fill,
                    "allowReplaceSourcePlaces": allow_replace_source_places,
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
                allow_finder_gap_fill=allow_finder_gap_fill,
                allow_replace_source_places=allow_replace_source_places,
                run_id=run_id,
                timing_trace=timing_trace,
                candidate_reviews=candidate_reviews,
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
        allow_finder_gap_fill: bool,
        allow_replace_source_places: bool,
        run_id: str | None,
        timing_trace: PlanTimingTrace | None,
        candidate_reviews: list[PlaceCandidateReview],
    ) -> Plan:
        region_key = normalize_region_key(intent.destination, explicit_region_key)
        theme_started = time.perf_counter()
        theme_output = await self.trip_theme_planner.create_trip_themes(
            intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            preference_profile=preference_profile,
        )
        if timing_trace is not None:
            timing_trace.add_stage(
                "tripThemePlanner",
                "TripThemePlanner xác định chủ đề toàn chuyến",
                theme_started,
                details={
                    "tripThemeCount": len(theme_output.trip_themes),
                    "selectedPlaceCount": len(selected_places),
                    "inputSelectedPlaceCount": len(selected_places),
                    "requiredExperienceCount": len(theme_output.required_experiences),
                    "dataSource": "Knowledge Graph DB + LLM",
                },
            )
        if self.planning_runs is not None and run_id is not None:
            self.planning_runs.add_stage(
                run_id,
                stage="trip_theme_planner",
                status=("completed" if theme_output.trip_themes_ready else "blocked"),
                duration_ms=int((time.perf_counter() - theme_started) * 1_000),
                input_data={
                    "intent": planning_intent,
                    "tripSpec": trip_spec,
                    "regionKey": region_key,
                    "selectedPlaces": selected_places,
                    "preferenceProfile": preference_profile,
                },
                output_data=theme_output,
                metadata={"trace": theme_output.trace},
            )
        if not theme_output.trip_themes_ready:
            raise AppError(
                422,
                "TRIP_THEME_INPUT_INSUFFICIENT",
                (
                    "Mình chưa thể lập lịch trình vì điểm đến này chưa có đủ địa điểm phù hợp; "
                    "bạn hãy chọn một địa điểm cụ thể hoặc thử điểm đến khác."
                ),
                {
                    "selectedPlaces": (
                        "Confirm at least one Place or seed the destination catalog."
                    )
                },
            )

        selection_candidates = self._filter_place_selection_candidates(
            selected_places,
            theme_output,
        )
        selection_input = PlaceSelectionInput(
            mode=PlanningMode.main,
            intent=planning_intent,
            tripSpec=theme_output.trip_spec,
            regionKey=region_key,
            tripThemes=theme_output.trip_themes,
            requiredExperiences=theme_output.required_experiences,
            selectedPlaces=selection_candidates,
            userStatus=user_status,
            allowFinderGapFill=allow_finder_gap_fill,
            allowReplaceSourcePlaces=allow_replace_source_places,
        )
        selection_started = time.perf_counter()
        selection_output = self.place_selector.fill_agent_plan(selection_input)
        if timing_trace is not None:
            timing_trace.add_stage(
                "placeSelector",
                "PlaceSelector chọn địa điểm và xếp tuyến",
                selection_started,
                details={
                    "scheduledDayCount": len(selection_output.final_days),
                    "selectedPlaceCount": len(selection_candidates),
                    "inputSelectedPlaceCount": len(selected_places),
                    "selectionCandidateCount": len(selection_candidates),
                    "requiredExperienceCount": len(theme_output.required_experiences),
                    "dataSource": "Knowledge Graph DB + deterministic rules",
                },
            )
        if self.planning_runs is not None and run_id is not None:
            self.planning_runs.add_stage(
                run_id,
                stage="place_selector",
                status=selection_output.trace.status.value,
                duration_ms=int((time.perf_counter() - selection_started) * 1_000),
                input_data=selection_input,
                output_data=selection_output,
                metadata={"trace": selection_output.trace},
            )
        assemble_started = time.perf_counter()
        fallback_recommendations = RouteAwareActivityFallback(
            self.place_selector.place_tool
        ).recommend(
            days=selection_output.final_days,
            reviews=candidate_reviews,
            region_key=region_key,
        )
        unscheduled_places = self._merge_unscheduled_places(
            theme_output,
            [*selection_output.unscheduled_places, *fallback_recommendations],
        )
        plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.main,
            status=PlanStatus.checking,
            title=f"Kế hoạch cho {intent.destination}",
            destination=intent.destination,
            intent=intent,
            tripThemes=theme_output.trip_themes,
            requiredExperiences=theme_output.required_experiences,
            days=selection_output.final_days,
            initialUserStatus=user_status,
            finalUserStatus=selection_output.final_user_status,
            finalPlanStatus=selection_output.final_plan_status,
            unscheduledPlaces=unscheduled_places,
            planningAssumptions=theme_output.assumptions,
            warnings=[
                *theme_output.warnings,
                *selection_output.warnings,
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
                    "dataSource": "In-memory plan assembly",
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
                    "dataSource": "Deterministic checker",
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

    def _filter_place_selection_candidates(
        self,
        selected_places: list[SelectedPlaceContext],
        planner_output: TripThemePlanningOutput,
    ) -> list[SelectedPlaceContext]:
        del planner_output
        return selected_places

    def _merge_unscheduled_places(
        self,
        planner_output: TripThemePlanningOutput,
        selection_unscheduled: list[UnscheduledPlace],
    ) -> list[UnscheduledPlace]:
        del planner_output
        merged = list(selection_unscheduled)
        unique: dict[str, UnscheduledPlace] = {}
        for item in merged:
            key = item.place_id or item.name.casefold()
            unique.setdefault(key, item)
        return list(unique.values())
