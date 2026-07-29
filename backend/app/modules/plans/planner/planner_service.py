from __future__ import annotations

import logging

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import CheckReport, MacroPlan, TravelIntent
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    AgentTrace,
    PlannerAgentInput,
    PlannerAgentOutput,
    PlannerResearchDraft,
    PlannerMacroPlanDraft,
    PlannerVerifiedResearch,
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
    PLANNER_RESEARCH_PROMPT_VERSION,
    PLANNER_RESEARCH_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    build_planner_repair_payload,
    build_planner_research_payload,
    build_planner_user_payload,
)
from app.modules.plans.planner.research_tool import (
    EmptyPlannerResearchTool,
    PlannerResearchTool,
)
from app.modules.plans.planner.region_context import (
    PlannerStatisticsProvider,
    load_region_statistics_context,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceDimension,
)

logger = logging.getLogger(__name__)
PLANNER_MAX_REPAIR_ATTEMPTS = 3


class PlannerService:
    def __init__(
        self,
        statistics_provider: PlannerStatisticsProvider,
        llm: LLMClient,
        research_tool: PlannerResearchTool | None = None,
    ) -> None:
        self.statistics_provider = statistics_provider
        self.llm = llm
        self.research_tool = research_tool or EmptyPlannerResearchTool()

    async def create_main_macro_plan(
        self,
        intent: TravelIntent,
        *,
        trip_spec: TripPlanningSpec,
        region_key: str,
        selected_places: list[SelectedPlaceContext],
        plan_state: PlanWorkingState | None = None,
        preference_profile: LongTermPreferenceProfile | None = None,
    ) -> PlannerAgentOutput:
        planner_input, statistics_status = self._build_input(
            mode=PlanningMode.main,
            intent=intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            plan_state=plan_state,
            preference_profile=preference_profile,
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
        preference_profile: LongTermPreferenceProfile | None = None,
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
            preference_profile=preference_profile,
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
        preference_profile: LongTermPreferenceProfile | None = None,
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
                preferenceProfile=(
                    preference_profile or LongTermPreferenceProfile()
                ),
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
            research_raw = await self.llm.generate_json(
                system_prompt=PLANNER_RESEARCH_SYSTEM_PROMPT,
                user_payload=build_planner_research_payload(planner_input),
            )
            research_draft = PlannerResearchDraft.model_validate_json(
                research_raw
            )
            verified_research = self.research_tool.verify(
                research_draft,
                root_region_key=planner_input.region_context.region_key,
            )
        except ValidationError as exc:
            raise RuntimeError(
                "LLM Planner returned an invalid research contract."
            ) from exc

        raw = await self.llm.generate_json(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_payload=build_planner_user_payload(
                planner_input,
                research_draft,
                verified_research,
            ),
        )
        repair_attempts = 0
        while True:
            try:
                draft = self._parse_and_validate_macro_draft(
                    planner_input,
                    raw,
                    research_draft,
                    verified_research,
                )
                break
            except (ValidationError, ValueError) as exc:
                feedback = self._validation_feedback(exc)
                if repair_attempts >= PLANNER_MAX_REPAIR_ATTEMPTS:
                    logger.warning(
                        "Planner MacroPlan contract remained invalid "
                        "after %s repair attempts: %s",
                        repair_attempts,
                        feedback,
                    )
                    raise RuntimeError(
                        "LLM Planner returned an invalid MacroPlan contract "
                        f"after {repair_attempts} repair attempts."
                    ) from exc

                repair_attempts += 1
                raw = await self.llm.generate_json(
                    system_prompt=PLANNER_SYSTEM_PROMPT,
                    user_payload=build_planner_repair_payload(
                        planner_input,
                        research_draft,
                        verified_research,
                        previous_output=raw,
                        validation_feedback=feedback,
                    ),
                )

        warnings = list(
            dict.fromkeys(
                [
                    *draft.warnings,
                    *verified_research.warnings,
                    *statistics_warnings,
                ]
            )
        )
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
                    f"repairAttempts={repair_attempts}",
                    f"researchPromptVersion={PLANNER_RESEARCH_PROMPT_VERSION}",
                    f"promptVersion={PLANNER_PROMPT_VERSION}",
                    f"statisticsStatus={statistics_status}",
                    (
                        "capabilityEvidenceCount="
                        f"{len(verified_research.capability_evidence)}"
                    ),
                    (
                        "nearbyRegionCount="
                        f"{len(verified_research.nearby_regions)}"
                    ),
                    (
                        "snapshotId="
                        f"{planner_input.region_context.snapshot_ref.snapshot_id}"
                    ),
                ],
            ),
        )

    def _parse_and_validate_macro_draft(
        self,
        planner_input: PlannerAgentInput,
        raw: str,
        research_draft: PlannerResearchDraft,
        verified_research: PlannerVerifiedResearch,
    ) -> PlannerMacroPlanDraft:
        draft = PlannerMacroPlanDraft.model_validate_json(raw)
        return self._validate_and_normalize_draft(
            planner_input,
            draft,
            research_draft,
            verified_research,
        )

    @staticmethod
    def _validation_feedback(exc: ValidationError | ValueError) -> str:
        if isinstance(exc, ValidationError):
            fields = [
                (
                    ".".join(str(part) for part in error["loc"])
                    + ":"
                    + str(error["type"])
                )
                for error in exc.errors()[:10]
            ]
            return "Schema validation failed at " + ", ".join(fields)
        return str(exc)

    def _validate_and_normalize_draft(
        self,
        planner_input: PlannerAgentInput,
        draft: PlannerMacroPlanDraft,
        research_draft: PlannerResearchDraft,
        verified_research: PlannerVerifiedResearch,
    ) -> PlannerMacroPlanDraft:
        macro = draft.macro_plan.model_copy(
            update={
                "destination": planner_input.intent.destination,
                "region_key": planner_input.region_context.region_key,
                "journey_style": research_draft.journey_style,
            }
        )
        draft = draft.model_copy(update={"macro_plan": macro})

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
            *(
                region.region_key
                for region in verified_research.nearby_regions
            ),
            *(
                region_key
                for evidence in verified_research.capability_evidence
                for region_key in evidence.region_keys
            ),
            *(
                place.region_key
                for place in planner_input.selected_places
                if place.region_key
            ),
        }
        for brief in macro.day_briefs:
            if brief.target_region_key not in allowed_regions:
                raise ValueError(
                    f"Unknown targetRegionKey: {brief.target_region_key}"
                )

        self._validate_journey_phases(
            macro,
            allowed_regions=allowed_regions,
            trip_days=planner_input.trip_spec.days,
            research_draft=research_draft,
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
        unknown_refs = (
            set(allocated_refs) | set(unallocated_refs)
        ) - set(selected_by_ref)
        if unknown_refs:
            normalized_briefs = [
                brief.model_copy(
                    update={
                        "allocated_selected_place_refs": [
                            ref
                            for ref in brief.allocated_selected_place_refs
                            if ref in selected_by_ref
                        ]
                    }
                )
                for brief in macro.day_briefs
            ]
            macro = macro.model_copy(
                update={"day_briefs": normalized_briefs}
            )
            draft = draft.model_copy(
                update={
                    "macro_plan": macro,
                    "unallocated_selected_places": [
                        item
                        for item in draft.unallocated_selected_places
                        if item.place.stable_ref in selected_by_ref
                    ],
                    "warnings": [
                        *draft.warnings,
                        (
                            "Planner đã trả tham chiếu địa điểm không có trong "
                            "selectedPlaces; backend đã loại bỏ tham chiếu này."
                        ),
                    ],
                }
            )
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

        missing_refs = [
            stable_ref
            for stable_ref in selected_by_ref
            if stable_ref not in set(accounted_refs)
        ]
        if missing_refs:
            repaired_unallocated = [
                *draft.unallocated_selected_places,
                *[
                    UnallocatedSelectedPlace(
                        place=selected_by_ref[stable_ref],
                        reasonCode="planner_omitted_selected_place",
                        reason=(
                            "Planner did not provide an allocation; the backend "
                            "preserved this selected Place as unallocated."
                        ),
                    )
                    for stable_ref in missing_refs
                ],
            ]
            draft = draft.model_copy(
                update={
                    "unallocated_selected_places": repaired_unallocated,
                    "warnings": [
                        *draft.warnings,
                        (
                            "Một số địa điểm đã chọn chưa được Planner phân bổ; "
                            "backend đã giữ chúng trong danh sách chưa xếp lịch."
                        ),
                    ],
                }
            )

        avoided_names = {
            name.strip().casefold()
            for name in planner_input.intent.avoid_places
        }
        excluded_names = {
            name.strip().casefold()
            for name in planner_input.plan_state.excluded_place_names
        }
        prohibited_names = avoided_names | excluded_names
        for ref in allocated_refs:
            place = selected_by_ref[ref]
            if place.name.strip().casefold() in prohibited_names:
                raise ValueError("An avoided or excluded Place was allocated.")

        normalized_unallocated: list[UnallocatedSelectedPlace] = []
        for item in draft.unallocated_selected_places:
            source_place = selected_by_ref[item.place.stable_ref]
            normalized = item.model_copy(update={"place": source_place})
            normalized_name = source_place.name.strip().casefold()
            if normalized_name in avoided_names:
                normalized = normalized.model_copy(
                    update={
                        "reason_code": "avoided_by_user",
                        "reason": "Place is explicitly avoided by the user.",
                    }
                )
            elif normalized_name in excluded_names:
                normalized = normalized.model_copy(
                    update={
                        "reason_code": "excluded_by_plan_state",
                        "reason": "Place is excluded from this planning scope.",
                    }
                )
            normalized_unallocated.append(normalized)
        return draft.model_copy(
            update={"unallocated_selected_places": normalized_unallocated}
        )

    def _validate_journey_phases(
        self,
        macro: MacroPlan,
        *,
        allowed_regions: set[str],
        trip_days: int,
        research_draft: PlannerResearchDraft,
    ) -> None:
        previous_end = 0
        for phase in macro.journey_phases:
            if phase.start_day > phase.end_day:
                raise ValueError("Journey phase startDay must not exceed endDay.")
            if phase.start_day <= previous_end:
                raise ValueError("Journey phases must be ordered and non-overlapping.")
            if phase.end_day > trip_days:
                raise ValueError("Journey phase exceeds requested trip duration.")
            if phase.base_region_key not in allowed_regions:
                raise ValueError(
                    f"Unknown journey phase regionKey: {phase.base_region_key}"
                )
            previous_end = phase.end_day

        if (
            trip_days >= 7
            and research_draft.journey_style in {"multi_base", "road_trip"}
            and len(macro.journey_phases) < 2
        ):
            raise ValueError(
                "Long multi-base or road-trip plans require at least two phases."
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
