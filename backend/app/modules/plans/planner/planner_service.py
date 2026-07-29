from __future__ import annotations

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import CheckReport, MacroPlan, TravelIntent
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    AgentTrace,
    PlannerAgentInput,
    PlannerAgentOutput,
    PlannerMacroPlanDraft,
    PlanningAgentName,
    PlanningAgentStatus,
    PlanningIntent,
    PlanningMode,
    PlanWorkingState,
    SelectedPlaceContext,
    TripPlanningSpec,
    UnallocatedSelectedPlace,
)
from app.modules.plans.planner.prompt import (
    PLANNER_PROMPT_VERSION,
    PLANNER_SYSTEM_PROMPT,
    build_planner_user_payload,
)
from app.modules.plans.planner.region_context import (
    PlannerStatisticsProvider,
    load_region_statistics_context,
)


class PlannerService:
    def __init__(
        self,
        statistics_provider: PlannerStatisticsProvider,
        llm: LLMClient,
    ) -> None:
        self.statistics_provider = statistics_provider
        self.llm = llm

    async def create_main_macro_plan(
        self,
        intent: TravelIntent,
        *,
        trip_spec: TripPlanningSpec,
        region_key: str,
        selected_places: list[SelectedPlaceContext],
        plan_state: PlanWorkingState | None = None,
    ) -> PlannerAgentOutput:
        planner_input, statistics_status = self._build_input(
            mode=PlanningMode.main,
            intent=intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            plan_state=plan_state,
        )
        return await self._create_plan(planner_input, statistics_status)

    async def create_backup_macro_plan(
        self,
        intent: TravelIntent,
        reason: str,
        *,
        trip_spec: TripPlanningSpec,
        region_key: str,
        selected_places: list[SelectedPlaceContext],
        original_macro_plan: MacroPlan,
        check_report: CheckReport | None = None,
    ) -> PlannerAgentOutput:
        planner_input, statistics_status = self._build_input(
            mode=PlanningMode.backup,
            intent=intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            original_macro_plan=AgentMacroPlan.model_validate(
                original_macro_plan.model_dump()
            ),
            check_report=check_report,
            plan_state=PlanWorkingState(warnings=[reason]),
        )
        return await self._create_plan(planner_input, statistics_status)

    def _build_input(
        self,
        *,
        mode: PlanningMode,
        intent: TravelIntent,
        trip_spec: TripPlanningSpec,
        region_key: str,
        selected_places: list[SelectedPlaceContext],
        plan_state: PlanWorkingState | None = None,
        original_macro_plan: AgentMacroPlan | None = None,
        check_report: CheckReport | None = None,
    ) -> tuple[PlannerAgentInput, str]:
        region_context, statistics_status = load_region_statistics_context(
            self.statistics_provider,
            region_key,
        )
        planning_intent = PlanningIntent(
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
        return (
            PlannerAgentInput(
                mode=mode,
                intent=planning_intent,
                tripSpec=trip_spec,
                regionContext=region_context,
                selectedPlaces=selected_places,
                planState=plan_state or PlanWorkingState(),
                originalMacroPlan=original_macro_plan,
                checkReport=check_report,
            ),
            statistics_status,
        )

    async def _create_plan(
        self,
        planner_input: PlannerAgentInput,
        statistics_status: str,
    ) -> PlannerAgentOutput:
        ready = (
            planner_input.region_context.active_place_count > 0
            or bool(planner_input.selected_places)
        )
        statistics_warnings = self._statistics_warnings(planner_input)
        if not ready:
            return PlannerAgentOutput(
                mode=planner_input.mode,
                macroPlan=AgentMacroPlan(
                    title=f"Kế hoạch cho {planner_input.intent.destination}",
                    destination=planner_input.intent.destination,
                    regionKey=planner_input.region_context.region_key,
                    dayBriefs=[],
                ),
                tripSpec=planner_input.trip_spec,
                dayBriefsReady=False,
                warnings=statistics_warnings,
                trace=AgentTrace(
                    agent=PlanningAgentName.planner,
                    status=PlanningAgentStatus.blocked,
                    summary=(
                        "Không có Place active hoặc địa điểm đã chọn để tạo "
                        "MacroPlan."
                    ),
                    notes=[
                        "generator=llm",
                        f"promptVersion={PLANNER_PROMPT_VERSION}",
                        (
                            "snapshotId="
                            f"{planner_input.region_context.snapshot_ref.snapshot_id}"
                        ),
                    ],
                ),
            )

        try:
            raw = await self.llm.generate_json(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_payload=build_planner_user_payload(planner_input),
            )
            draft = PlannerMacroPlanDraft.model_validate_json(raw)
            draft = self._validate_and_normalize_draft(planner_input, draft)
        except (ValidationError, ValueError) as exc:
            raise RuntimeError(
                "LLM Planner returned an invalid MacroPlan contract."
            ) from exc

        warnings = list(dict.fromkeys([*draft.warnings, *statistics_warnings]))
        return PlannerAgentOutput(
            mode=planner_input.mode,
            macroPlan=draft.macro_plan,
            tripSpec=planner_input.trip_spec,
            dayBriefsReady=True,
            unallocatedSelectedPlaces=draft.unallocated_selected_places,
            assumptions=draft.assumptions,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.planner,
                status=PlanningAgentStatus.completed,
                summary="AI đã tạo MacroPlan từ context và thống kê khu vực nhỏ.",
                notes=[
                    "generator=llm",
                    f"promptVersion={PLANNER_PROMPT_VERSION}",
                    f"statisticsStatus={statistics_status}",
                    (
                        "snapshotId="
                        f"{planner_input.region_context.snapshot_ref.snapshot_id}"
                    ),
                ],
            ),
        )

    def _validate_and_normalize_draft(
        self,
        planner_input: PlannerAgentInput,
        draft: PlannerMacroPlanDraft,
    ) -> PlannerMacroPlanDraft:
        macro = draft.macro_plan
        if macro.destination != planner_input.intent.destination:
            raise ValueError("MacroPlan destination must match Planner input.")
        if macro.region_key != planner_input.region_context.region_key:
            raise ValueError("MacroPlan regionKey must match the statistics root.")

        expected_days = list(range(1, planner_input.trip_spec.days + 1))
        actual_days = [brief.day for brief in macro.day_briefs]
        if actual_days != expected_days:
            raise ValueError("MacroPlan must contain consecutive requested days.")

        allowed_regions = {
            planner_input.region_context.region_key,
            *(
                str(area.get("regionKey"))
                for area in planner_input.region_context.area_profiles
                if area.get("regionKey")
            ),
            *(
                str(area.get("regionKey"))
                for area in planner_input.region_context.planner_signals.get(
                    "candidateAreas",
                    [],
                )
                if area.get("regionKey")
            ),
        }
        for brief in macro.day_briefs:
            if brief.target_region_key not in allowed_regions:
                raise ValueError(
                    f"Unknown targetRegionKey: {brief.target_region_key}"
                )

        selected_by_ref = {
            place.stable_ref: place for place in planner_input.selected_places
        }
        allocated_refs = [
            ref
            for brief in macro.day_briefs
            for ref in brief.allocated_selected_place_refs
        ]
        unallocated_refs = [
            item.place.stable_ref
            for item in draft.unallocated_selected_places
        ]
        accounted_refs = [*allocated_refs, *unallocated_refs]
        if len(accounted_refs) != len(set(accounted_refs)):
            raise ValueError("A selected Place was allocated more than once.")
        if set(accounted_refs) != set(selected_by_ref):
            raise ValueError(
                "Every selected Place must be allocated or explicitly unallocated."
            )

        prohibited_names = {
            *(
                name.strip().casefold()
                for name in planner_input.intent.avoid_places
            ),
            *(
                name.strip().casefold()
                for name in planner_input.plan_state.excluded_place_names
            ),
        }
        for ref in allocated_refs:
            place = selected_by_ref[ref]
            if place.name.strip().casefold() in prohibited_names:
                raise ValueError("An avoided or excluded Place was allocated.")

        normalized_unallocated: list[UnallocatedSelectedPlace] = []
        for item in draft.unallocated_selected_places:
            source_place = selected_by_ref[item.place.stable_ref]
            normalized_unallocated.append(
                item.model_copy(update={"place": source_place})
            )
        return draft.model_copy(
            update={"unallocated_selected_places": normalized_unallocated}
        )

    def _statistics_warnings(
        self,
        planner_input: PlannerAgentInput,
    ) -> list[str]:
        context = planner_input.region_context
        warnings: list[str] = []
        if context.active_place_count == 0:
            warnings.append(
                f"Không có Place active cho {context.region_key}; Finder chỉ "
                "có thể dùng các địa điểm người dùng đã chọn."
            )
            return warnings

        eligible_quality = context.planner_eligible.get(
            "dataQuality",
            context.data_quality,
        )
        missing_hours = int(eligible_quality.get("missingOpeningHours", 0))
        if missing_hours > context.active_place_count / 2:
            warnings.append(
                "Hơn một nửa Place active chưa có giờ mở cửa; Finder phải "
                "xác minh tính khả thi theo thời gian."
            )
        stale_data = int(eligible_quality.get("staleOperationalData", 0))
        if stale_data:
            warnings.append(
                f"{stale_data} Place active có dữ liệu vận hành đã cũ."
            )
        return warnings
