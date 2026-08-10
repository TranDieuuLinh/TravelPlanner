import time
from typing import Callable
from uuid import uuid4

from app.integrations.llm.tracing import observe_application
from app.modules.planning_runs.repository import PlanningRunRepository
from app.modules.plans.checks.overall_checker import OverallChecker
from app.modules.plans.domain.entities import (
    Plan,
    RouteEnrichmentContext,
    TravelIntent,
    UnscheduledPlace,
    UserStatus,
)
from app.modules.plans.domain.plan_notes import PlanNoteSource
from app.modules.plans.domain.enums import PlanKind, PlanStatus
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    PlaceSelectionInput,
    PlanningAgentName,
    PlanningAgentStatus,
    TripThemePlanningOutput,
    PlanningIntent,
    PlanningMode,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.explorer.explorer_service import ExplorerService
from app.modules.plans.explorer.schema import PlaceCandidateReview
from app.modules.plans.place_selector.service import PlaceSelectorService
from app.modules.plans.solver.candidate_pool import (
    build_selected_place_pool,
    selected_place_identity,
)
from app.modules.plans.solver.cluster_first_repair import ClusterFirstRepairSolver
from app.modules.plans.solver.contracts import PlanningSolver
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
from app.modules.plans.timing import (
    PlanTimingReport,
    PlanTimingSubstage,
    PlanTimingTrace,
)


class MainPlanWorkflow:
    def __init__(
        self,
        explorer: ExplorerService,
        trip_theme_planner: TripThemePlannerService,
        place_selector: PlaceSelectorService,
        checker: OverallChecker | None = None,
        planning_runs: PlanningRunRepository | None = None,
        planning_solver: PlanningSolver | None = None,
    ) -> None:
        self.explorer = explorer
        self.trip_theme_planner = trip_theme_planner
        self.place_selector = place_selector
        self.checker = checker or OverallChecker()
        self.planning_runs = planning_runs
        self.planning_solver = planning_solver or ClusterFirstRepairSolver()

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
            region_stories=[],
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
        reuse_theme_plan: Plan | None = None,
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
            region_stories=payload.region_stories,
            user_id=(
                int(payload.user_id)
                if payload.user_id and payload.user_id.isdigit()
                else None
            ),
            intake_id=payload.intake_id,
            reuse_theme_plan=reuse_theme_plan,
            expand_days_to_fit_mandatory_places=(
                payload.expand_days_to_fit_selected_places
            ),
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
            region_stories=[],
        )

    @observe_application("planner.main_plan")
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
        region_stories: list[PlanNoteSource],
        user_id: int | None = None,
        intake_id: str | None = None,
        timing_trace: PlanTimingTrace | None = None,
        reuse_theme_plan: Plan | None = None,
        expand_days_to_fit_mandatory_places: bool = False,
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
                region_stories=region_stories,
                reuse_theme_plan=reuse_theme_plan,
                expand_days_to_fit_mandatory_places=(
                    expand_days_to_fit_mandatory_places
                ),
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

    @observe_application("planner.execute_plan")
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
        region_stories: list[PlanNoteSource],
        reuse_theme_plan: Plan | None = None,
        expand_days_to_fit_mandatory_places: bool = False,
    ) -> Plan:
        region_key = normalize_region_key(intent.destination, explicit_region_key)
        theme_started = time.perf_counter()
        theme_sub_stages: list[PlanTimingSubstage] = []
        if reuse_theme_plan is None:
            theme_output = await self.trip_theme_planner.create_trip_themes(
                intent,
                trip_spec=trip_spec,
                region_key=region_key,
                selected_places=selected_places,
                preference_profile=preference_profile,
                on_timing_stage=(
                    theme_sub_stages.append if timing_trace is not None else None
                ),
            )
        else:
            theme_output = TripThemePlanningOutput(
                mode=PlanningMode.main,
                tripSpec=trip_spec,
                tripThemes=reuse_theme_plan.trip_themes,
                requiredExperiences=reuse_theme_plan.required_experiences,
                assumptions=reuse_theme_plan.planning_assumptions,
                warnings=[],
                trace=AgentTrace(
                    agent=PlanningAgentName.trip_theme_planner,
                    status=PlanningAgentStatus.completed,
                    summary="Tái sử dụng theme vì đầu vào theme không đổi.",
                    notes=["themeReuse=true"],
                ),
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
                    "dataSource": (
                        "Plan revision trước"
                        if reuse_theme_plan is not None
                        else "Knowledge Graph DB + LLM"
                    ),
                    "reused": reuse_theme_plan is not None,
                },
                sub_stages=theme_sub_stages,
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
                metadata={
                    "trace": theme_output.trace,
                    "reused": reuse_theme_plan is not None,
                },
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
        initial_selection_input = PlaceSelectionInput(
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
        mandatory_pool_started = time.perf_counter()
        prepared_input, unresolved_requirements = (
            self.place_selector.prepare_mandatory_candidates(
                initial_selection_input
            )
        )
        mandatory_places = list(prepared_input.selected_places)
        if timing_trace is not None:
            timing_trace.add_stage(
                "mandatoryCandidatePool",
                "Tập hợp địa điểm bắt buộc",
                mandatory_pool_started,
                details={
                    "sourceAndUserPlaceCount": len(selection_candidates),
                    "resolvedRequiredExperienceCount": (
                        len(mandatory_places) - len(selection_candidates)
                    ),
                    "unresolvedRequiredExperienceCount": len(
                        unresolved_requirements
                    ),
                    "optionalSuggestionCount": 0,
                },
            )

        capacity_started = time.perf_counter()
        mandatory_pool = build_selected_place_pool(mandatory_places)
        optimizer = getattr(self.place_selector, "route_optimizer", None)
        matrix_provider = getattr(optimizer, "matrix_provider", None)
        solution = self.planning_solver.solve(
            mandatory_pool,
            requested_days=trip_spec.days,
            days_locked=not expand_days_to_fit_mandatory_places,
            matrix_provider=matrix_provider,
        )
        assigned_days = solution.candidate_day
        overflow_ids = set(solution.unscheduled_candidate_ids)
        capacity_unscheduled = [
            self._capacity_unscheduled(place)
            for place in mandatory_places
            if selected_place_identity(place) in overflow_ids
        ]
        schedulable_places = [
            place.model_copy(
                update={
                    "source_day": assigned_days.get(
                        selected_place_identity(place)
                    )
                    or place.source_day,
                }
            )
            for place in mandatory_places
            if selected_place_identity(place) not in overflow_ids
        ]
        if solution.day_count != trip_spec.days:
            trip_spec = trip_spec.model_copy(
                update={"days": solution.day_count}
            )
            intent = intent.model_copy(update={"days": solution.day_count})
        selection_input = prepared_input.model_copy(
            update={
                "trip_spec": trip_spec,
                "selected_places": schedulable_places,
            }
        )
        if timing_trace is not None:
            timing_trace.add_stage(
                "capacityDayAllocation",
                "Kiểm tra sức chứa và phân bổ ngày",
                capacity_started,
                details={
                    "mandatoryCandidateCount": len(mandatory_pool.candidates),
                    "requestedDays": theme_output.trip_spec.days,
                    "selectedDays": solution.day_count,
                    "daysLocked": not expand_days_to_fit_mandatory_places,
                    "unscheduledMandatoryCount": len(capacity_unscheduled),
                    "matrixProvider": solution.matrix.provider,
                },
            )
        selection_started = time.perf_counter()
        defer_route_enrichment = bool(
            getattr(self.place_selector.route_optimizer, "supports_fixed_anchors", False)
        )
        selection_output = self.place_selector.fill_agent_plan(
            selection_input,
            enrich_routes=not defer_route_enrichment,
            requirements_prepared=True,
            unresolved_requirements=[
                *unresolved_requirements,
                *capacity_unscheduled,
            ],
        )
        if timing_trace is not None:
            timing_trace.add_stage(
                "lazyGapFillTimeline",
                "Lấp khoảng trống, xếp thứ tự và tạo timeline",
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
        review_unscheduled = self._needs_review_unscheduled(candidate_reviews)
        unscheduled_places = self._merge_unscheduled_places(
            theme_output,
            [*selection_output.unscheduled_places, *review_unscheduled],
        )
        plan = Plan(
            id=str(uuid4()),
            kind=PlanKind.main,
            status=PlanStatus.checking,
            title=f"Kế hoạch cho {intent.destination}",
            destination=intent.destination,
            regionStories=region_stories,
            intent=intent,
            tripThemes=theme_output.trip_themes,
            requiredExperiences=theme_output.required_experiences,
            # Day themes are no longer part of the planning/output contract.
            # Clear the legacy compatibility field at the assembly boundary.
            days=[
                day.model_copy(update={"theme": None})
                for day in selection_output.final_days
            ],
            initialUserStatus=user_status,
            finalUserStatus=selection_output.final_user_status,
            finalPlanStatus=selection_output.final_plan_status,
            unscheduledPlaces=unscheduled_places,
            planningAssumptions=theme_output.assumptions,
            warnings=[
                *theme_output.warnings,
                *selection_output.warnings,
            ],
            routeEnrichmentStatus=(
                "pending" if defer_route_enrichment else "completed"
            ),
            routeEnrichmentContext=(
                RouteEnrichmentContext(
                    tripStartDate=trip_spec.start_date,
                    preferredModes=[
                        mode.value for mode in trip_spec.transport.preferred_modes
                    ],
                    avoidModes=[
                        mode.value for mode in trip_spec.transport.avoid_modes
                    ],
                )
                if defer_route_enrichment
                else None
            ),
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
            and plan.route_enrichment_status == "completed"
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
            key = item.candidate_id or item.place_id or item.name.casefold()
            unique.setdefault(key, item)
        return list(unique.values())

    @staticmethod
    def _capacity_unscheduled(place: SelectedPlaceContext) -> UnscheduledPlace:
        return UnscheduledPlace(
            placeId=place.place_id,
            name=place.name,
            day=place.source_day,
            reasonCode="no_day_capacity",
            reason=(
                "Địa điểm bắt buộc không còn đủ sức chứa trong số ngày đã khóa."
            ),
            address=place.address,
            latitude=place.latitude,
            longitude=place.longitude,
            tags=place.tags,
            sourceRefs=place.source_refs,
            sourceProvider=place.source_provider,
            sourceActivity=place.source_activity,
        )

    @staticmethod
    def _needs_review_unscheduled(
        reviews: list[PlaceCandidateReview],
    ) -> list[UnscheduledPlace]:
        """Keep unresolved URL venues visible without inventing a replacement.

        A ``needs_review`` venue is an identity decision, not an activity-name
        query.  The user must choose one of its resolver matches before it can
        become a schedulable Place.
        """

        output: list[UnscheduledPlace] = []
        for review in reviews:
            if review.status != "needs_review":
                continue
            reason = (
                "Cần chọn đúng địa điểm từ các kết quả khớp trước khi thêm "
                "vào lịch trình."
                if review.top_matches
                else "Chưa xác định được địa điểm cụ thể từ nguồn URL."
            )
            output.append(
                UnscheduledPlace(
                    candidateId=review.candidate_id,
                    name=review.name,
                    day=review.source_day,
                    reasonCode="identity_needs_review",
                    reason=reason,
                    placeType=review.category.value,
                    sourceRefs=review.source_urls,
                    sourceProvider=review.provider,
                    sourceActivity=review.source_activity,
                    topMatches=[
                        match.model_dump(mode="json", by_alias=True)
                        for match in review.top_matches
                    ],
                )
            )
        return output
