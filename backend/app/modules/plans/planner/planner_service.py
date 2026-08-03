from __future__ import annotations

import logging

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import (
    CheckReport,
    DayBrief,
    MacroPlan,
    TravelIntent,
    TripThemeRequirement,
)
from app.modules.plans.domain.constraint_policy import constraint_policy_rejection
from app.modules.plans.explorer.place_policy import is_meal_place
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
from app.modules.plans.planner.research_tools_orchestrator import ResearchToolsOrchestrator
from app.modules.plans.planner.research_tools_schema import (
    ConstraintResearchInput,
    FestivalDiscoveryInput,
    RegionOverviewInput,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
)

logger = logging.getLogger(__name__)
PLANNER_MAX_REPAIR_ATTEMPTS = 3

CONSTRAINT_RADIUS_KM = 50.0


def _build_constraint_input(
    *,
    planner_input: PlannerAgentInput,
    trip_spec: TripPlanningSpec,
) -> ConstraintResearchInput | None:
    """Build a ``ConstraintResearchInput`` that the schema will accept.

    The research tool requires real coordinates when ``mode='coordinates'``.
    When the planner has no geocoded location we fall back to ``mode='text'``
    and forward the destination string. Returns ``None`` when neither
    option can be satisfied so the caller skips the tool entirely.
    """

    interests = list(planner_input.intent.interests or [])
    budget = getattr(trip_spec.budget, "target_amount", None) if trip_spec.budget else None
    duration = trip_spec.days

    center = _centroid_from_selected_places(planner_input.selected_places)
    if center is not None:
        center_lat, center_lng = center
        return ConstraintResearchInput.model_validate(
            {
                "mode": "coordinates",
                "centerLat": center_lat,
                "centerLng": center_lng,
                "radiusKm": CONSTRAINT_RADIUS_KM,
                "budget": budget,
                "duration": duration,
                "interests": interests,
            }
        )

    query = (planner_input.intent.destination or "").strip()
    if not query:
        return None

    return ConstraintResearchInput.model_validate(
        {
            "mode": "text",
            "query": query,
            "budget": budget,
            "duration": duration,
            "interests": interests,
        }
    )


def _centroid_from_selected_places(
    selected_places: list[SelectedPlaceContext],
) -> tuple[float, float] | None:
    """Return the average latitude/longitude of selected places, if available."""

    coords: list[tuple[float, float]] = []
    for place in selected_places:
        latitude = getattr(place, "latitude", None)
        longitude = getattr(place, "longitude", None)
        if latitude is None or longitude is None:
            continue
        try:
            coords.append((float(latitude), float(longitude)))
        except (TypeError, ValueError):
            continue
    if not coords:
        return None
    average_lat = sum(lat for lat, _ in coords) / len(coords)
    average_lng = sum(lng for _, lng in coords) / len(coords)
    return average_lat, average_lng


class PlannerService:
    def __init__(
        self,
        statistics_provider: PlannerStatisticsProvider,
        llm: LLMClient,
        research_tool: PlannerResearchTool | None = None,
        research_tools: ResearchToolsOrchestrator | None = None,
    ) -> None:
        self.statistics_provider = statistics_provider
        self.llm = llm
        self.research_tool = research_tool or EmptyPlannerResearchTool()
        self.research_tools = research_tools

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

    async def create_from_agent_input(
        self,
        planner_input: PlannerAgentInput,
    ) -> PlannerAgentOutput:
        """Execute the real Planner against an explicit evaluation contract."""
        return await self._create_plan(
            planner_input,
            "provided_evaluation_context",
        )

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

    def _run_research_tools(
        self,
        planner_input: PlannerAgentInput,
    ) -> PlannerAgentInput:
        """
        Run research tools and populate tool results into planner_input.
        
        This method executes:
        1. region_overview - for overview statistics
        2. constraint_research - if coordinates/interests provided
        3. festival_discovery - for seasonal planning
        """
        if self.research_tools is None:
            return planner_input

        region_key = planner_input.region_context.region_key
        trip_spec = planner_input.trip_spec

        # 1. Always run region_overview for base statistics
        try:
            overview_result = self.research_tools.region_overview(
                RegionOverviewInput(region_key=region_key)
            )
            planner_input.region_overview = overview_result.model_dump(by_alias=True)
        except Exception as e:
            logger.warning("region_overview tool failed: %s", e)

        # 2. Run constraint_research if we have coordinates or interests
        has_constraints = (
            planner_input.intent.constraints
            or planner_input.intent.interests
            or trip_spec.budget
        )
        if has_constraints and self.research_tools:
            try:
                constraint_input = _build_constraint_input(
                    planner_input=planner_input,
                    trip_spec=trip_spec,
                )
                if constraint_input is not None:
                    result = self.research_tools.constraint_research(constraint_input)
                    planner_input.constraint_research = result.model_dump(by_alias=True)
            except Exception:
                logger.exception("constraint_research tool failed")

        # 3. Run festival_discovery for seasonal awareness
        try:
            # Extract month from start_date if available
            month = None
            if trip_spec.start_date:
                # Parse date like "2026-04-15"
                parts = trip_spec.start_date.split("-")
                if len(parts) >= 2:
                    month = f"tháng {int(parts[1])}"

            festival_result = self.research_tools.festival_discovery(
                FestivalDiscoveryInput(month=month)
            )
            planner_input.festival_discovery = festival_result.model_dump(by_alias=True)
        except Exception as e:
            logger.warning("festival_discovery tool failed: %s", e)

        return planner_input

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
                tripThemesReady=False,
                warnings=statistics_warnings,
                trace=AgentTrace(
                    agent=PlanningAgentName.planner,
                    status=PlanningAgentStatus.blocked,
                    summary=(
                        "Không có Place active hoặc địa điểm đã chọn để tạo "
                        "TripThemePlan."
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

        # Run research tools to populate tool results
        planner_input = self._run_research_tools(planner_input)

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
            tripThemesReady=True,
            unallocatedSelectedPlaces=draft.unallocated_selected_places,
            assumptions=draft.assumptions,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.planner,
                status=PlanningAgentStatus.completed,
                summary=(
                    "TripThemePlanner đã tạo yêu cầu trải nghiệm "
                    "toàn chuyến từ context và thống kê khu vực."
                ),
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
        macro = self._project_trip_themes_to_route_buckets(planner_input, macro)
        macro, themes_normalized = self._fit_trip_themes_to_activity_capacity(
            planner_input,
            macro,
        )
        draft = draft.model_copy(update={"macro_plan": macro})
        if themes_normalized:
            draft = draft.model_copy(
                update={
                    "warnings": [
                        *draft.warnings,
                        (
                            "Yêu cầu chủ đề đã được chuẩn hóa theo sức chứa hai "
                            "hoạt động chính mỗi ngày; điểm ăn uống được dành cho "
                            "các khung bữa ăn riêng."
                        ),
                    ]
                }
            )

        expected_days = list(range(1, planner_input.trip_spec.days + 1))
        actual_days = [brief.day for brief in macro.day_briefs]
        if actual_days != expected_days:
            raise ValueError("MacroPlan must contain consecutive requested days.")
        if sum(
            requirement.minimum_activities
            for requirement in macro.trip_themes
        ) > planner_input.trip_spec.days * 2:
            raise ValueError(
                "Trip theme requirements exceed the two-activity daily capacity."
            )

        if planner_input.intent.destination_stays:
            stay_by_day = {
                day: stay
                for stay in planner_input.intent.destination_stays
                for day in range(stay.start_day, stay.end_day + 1)
            }
            normalized_briefs = []
            for brief in macro.day_briefs:
                stay = stay_by_day.get(brief.day)
                if stay is None:
                    normalized_briefs.append(brief)
                    continue
                theme = brief.theme
                if stay.name.casefold() not in theme.casefold():
                    theme = f"{stay.name} · {theme}"
                normalized_briefs.append(
                    brief.model_copy(
                        update={
                            "target_area": stay.name,
                            "theme": theme,
                        }
                    )
                )
            macro = macro.model_copy(
                update={"day_briefs": normalized_briefs}
            )
            draft = draft.model_copy(update={"macro_plan": macro})

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
        for requirement in macro.trip_themes:
            unknown_theme_regions = (
                set(requirement.target_region_keys) - allowed_regions
            )
            if unknown_theme_regions:
                raise ValueError(
                    "Trip theme references an unknown targetRegionKey: "
                    f"{sorted(unknown_theme_regions)[0]}"
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

        policy_rejections = {
            ref: rejection
            for ref in allocated_refs
            if (
                rejection := constraint_policy_rejection(
                    planner_input.intent.constraint_policy,
                    name=selected_by_ref[ref].name,
                    place_type="selected_place",
                    tags=selected_by_ref[ref].tags,
                    region_key=selected_by_ref[ref].region_key,
                )
            )
            is not None
        }
        if policy_rejections:
            normalized_briefs = [
                brief.model_copy(
                    update={
                        "allocated_selected_place_refs": [
                            ref
                            for ref in brief.allocated_selected_place_refs
                            if ref not in policy_rejections
                        ]
                    }
                )
                for brief in macro.day_briefs
            ]
            existing_unallocated = {
                item.place.stable_ref
                for item in draft.unallocated_selected_places
            }
            policy_unallocated = [
                UnallocatedSelectedPlace(
                    place=selected_by_ref[ref],
                    reasonCode=rejection[0],
                    reason=rejection[1],
                )
                for ref, rejection in policy_rejections.items()
                if ref not in existing_unallocated
            ]
            macro = macro.model_copy(update={"day_briefs": normalized_briefs})
            draft = draft.model_copy(
                update={
                    "macro_plan": macro,
                    "unallocated_selected_places": [
                        *draft.unallocated_selected_places,
                        *policy_unallocated,
                    ],
                    "warnings": [
                        *draft.warnings,
                        (
                            "Một số địa điểm đã chọn vi phạm ràng buộc cứng và "
                            "được giữ trong danh sách chưa xếp lịch."
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

        draft = self._normalize_source_itinerary_allocations(
            planner_input,
            draft,
            selected_by_ref=selected_by_ref,
        )
        draft = self._enforce_day_activity_capacity(
            planner_input,
            draft,
            selected_by_ref=selected_by_ref,
        )
        macro = draft.macro_plan
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

    @staticmethod
    def _fit_trip_themes_to_activity_capacity(
        planner_input: PlannerAgentInput,
        macro: AgentMacroPlan,
    ) -> tuple[AgentMacroPlan, bool]:
        """Keep meal interests out of the two-main-activities budget."""
        capacity = planner_input.trip_spec.days * 2
        remaining = capacity
        normalized: list[TripThemeRequirement] = []
        changed = False
        for requirement in macro.trip_themes:
            meal_tags = [
                tag
                for tag in requirement.focus_tags
                if is_meal_place(tags=[tag])
            ]
            non_meal_tags = [
                tag
                for tag in requirement.focus_tags
                if not is_meal_place(tags=[tag])
            ]
            if (
                bool(meal_tags)
                and not non_meal_tags
            ) or (
                not requirement.focus_tags
                and is_meal_place(
                    tags=[],
                    source_activity=requirement.theme,
                )
            ):
                changed = True
                continue
            if remaining <= 0:
                changed = True
                continue
            minimum = min(requirement.minimum_activities, remaining)
            focus_tags = non_meal_tags or requirement.focus_tags
            changed = (
                changed
                or minimum != requirement.minimum_activities
                or focus_tags != requirement.focus_tags
            )
            normalized.append(
                requirement.model_copy(
                    update={
                        "minimum_activities": minimum,
                        "focus_tags": focus_tags,
                    }
                )
            )
            remaining -= minimum

        if not normalized:
            normalized = [
                TripThemeRequirement(
                    theme="Khám phá địa phương",
                    focusTags=["local"],
                    minimumActivities=1,
                )
            ]
            changed = True
        normalized_tags = list(
            dict.fromkeys(
                tag
                for requirement in normalized
                for tag in requirement.focus_tags
            )
        )
        day_briefs = [
            brief.model_copy(update={"focus_tags": normalized_tags})
            if brief.theme == "Tối ưu theo tuyến"
            else brief
            for brief in macro.day_briefs
        ]
        return (
            macro.model_copy(
                update={
                    "trip_themes": normalized,
                    "day_briefs": day_briefs,
                }
            ),
            changed,
        )

    @staticmethod
    def _project_trip_themes_to_route_buckets(
        planner_input: PlannerAgentInput,
        macro: AgentMacroPlan,
    ) -> AgentMacroPlan:
        """Create compatibility day buckets without assigning themes to days."""

        trip_themes = list(macro.trip_themes)
        if not trip_themes:
            seen: set[tuple[str, tuple[str, ...]]] = set()
            for brief in macro.day_briefs:
                key = (brief.theme.casefold(), tuple(brief.focus_tags))
                if key in seen:
                    continue
                seen.add(key)
                trip_themes.append(
                    TripThemeRequirement(
                        theme=brief.theme,
                        focusTags=brief.focus_tags,
                        minimumActivities=1,
                        targetRegionKeys=(
                            [brief.target_region_key]
                            if brief.target_region_key
                            else []
                        ),
                    )
                )
        if not trip_themes:
            trip_themes = [
                TripThemeRequirement(
                    theme=interest,
                    focusTags=[interest],
                    minimumActivities=1,
                )
                for interest in planner_input.intent.interests
            ] or [
                TripThemeRequirement(
                    theme="Trải nghiệm địa phương",
                    focusTags=["local"],
                    minimumActivities=1,
                )
            ]

        # Legacy LLM/test payloads may still provide dayBriefs. Preserve them as
        # an adapter. New v4 responses leave the list empty and take this path.
        if macro.day_briefs:
            return macro.model_copy(update={"trip_themes": trip_themes})

        all_tags = list(
            dict.fromkeys(
                tag
                for requirement in trip_themes
                for tag in requirement.focus_tags
            )
        )
        allocated_by_day: dict[int, list[str]] = {
            day: [] for day in range(1, planner_input.trip_spec.days + 1)
        }
        next_day = 1
        for place in sorted(
            planner_input.selected_places,
            key=lambda value: (
                value.source_day or 10_000,
                value.source_order or 10_000,
                value.name.casefold(),
            ),
        ):
            day = (
                place.source_day
                if place.source_day is not None
                and place.source_day in allocated_by_day
                else next_day
            )
            if len(allocated_by_day[day]) >= 2:
                available_day = next(
                    (
                        candidate_day
                        for candidate_day, refs in allocated_by_day.items()
                        if len(refs) < 2
                    ),
                    None,
                )
                if available_day is None:
                    continue
                day = available_day
            allocated_by_day[day].append(place.stable_ref)
            next_day = day % planner_input.trip_spec.days + 1

        stay_by_day = {
            day: stay
            for stay in planner_input.intent.destination_stays
            for day in range(stay.start_day, stay.end_day + 1)
        }
        route_buckets = [
            DayBrief(
                day=day,
                theme="Tối ưu theo tuyến",
                targetArea=(
                    stay_by_day[day].name
                    if day in stay_by_day
                    else planner_input.intent.destination
                ),
                targetRegionKey=planner_input.region_context.region_key,
                focusTags=all_tags,
                allocatedSelectedPlaceRefs=allocated_by_day[day],
                notes=[
                    "Compatibility bucket; themes and Places are not owned by this day."
                ],
            )
            for day in range(1, planner_input.trip_spec.days + 1)
        ]
        return macro.model_copy(
            update={"trip_themes": trip_themes, "day_briefs": route_buckets}
        )

    def _enforce_day_activity_capacity(
        self,
        planner_input: PlannerAgentInput,
        draft: PlannerMacroPlanDraft,
        *,
        selected_by_ref: dict[str, SelectedPlaceContext],
    ) -> PlannerMacroPlanDraft:
        activity_capacity = 2
        meal_capacity = 3
        overflow_refs: list[str] = []
        normalized_briefs = []
        for brief in draft.macro_plan.day_briefs:
            kept_refs: list[str] = []
            activity_count = 0
            meal_count = 0
            for ref in brief.allocated_selected_place_refs:
                place = selected_by_ref.get(ref)
                meal = bool(
                    place
                    and is_meal_place(
                        tags=place.tags,
                        source_activity=place.source_activity,
                    )
                )
                if meal and meal_count < meal_capacity:
                    kept_refs.append(ref)
                    meal_count += 1
                elif not meal and activity_count < activity_capacity:
                    kept_refs.append(ref)
                    activity_count += 1
                else:
                    overflow_refs.append(ref)
            normalized_briefs.append(
                brief.model_copy(
                    update={
                        "allocated_selected_place_refs": kept_refs
                    }
                )
            )
        if not overflow_refs:
            return draft

        existing_unallocated_refs = {
            item.place.stable_ref
            for item in draft.unallocated_selected_places
        }
        overflow_unallocated = [
            UnallocatedSelectedPlace(
                place=selected_by_ref[ref],
                reasonCode="no_day_capacity",
                reason=(
                    "Route-first allows at most two main activities and three "
                    "meal stops per day."
                ),
            )
            for ref in overflow_refs
            if ref in selected_by_ref and ref not in existing_unallocated_refs
        ]
        return draft.model_copy(
            update={
                "macro_plan": draft.macro_plan.model_copy(
                    update={"day_briefs": normalized_briefs}
                ),
                "unallocated_selected_places": [
                    *draft.unallocated_selected_places,
                    *overflow_unallocated,
                ],
                "warnings": [
                    *draft.warnings,
                    (
                        "Một số địa điểm vượt sức chứa hoạt động theo pace và "
                        "được giữ trong danh sách chưa xếp lịch."
                    ),
                ],
            }
        )

    def _normalize_source_itinerary_allocations(
        self,
        planner_input: PlannerAgentInput,
        draft: PlannerMacroPlanDraft,
        *,
        selected_by_ref: dict[str, SelectedPlaceContext],
    ) -> PlannerMacroPlanDraft:
        source_places = sorted(
            (
                place
                for place in planner_input.selected_places
                if place.source_order is not None
            ),
            key=lambda place: (
                place.source_order or 10_000,
                place.name.casefold(),
            ),
        )
        if not source_places:
            return draft

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
        eligible_places = [
            place
            for place in source_places
            if place.name.strip().casefold() not in prohibited_names
            and constraint_policy_rejection(
                planner_input.intent.constraint_policy,
                name=place.name,
                place_type="selected_place",
                tags=place.tags,
                region_key=place.region_key,
            )
            is None
        ]
        if not eligible_places:
            return draft

        trip_days = planner_input.trip_spec.days
        activity_capacity = 2
        meal_capacity = 3
        assigned_days: dict[str, int] = {}
        out_of_range: list[SelectedPlaceContext] = []
        over_capacity: list[SelectedPlaceContext] = []
        source_refs = {place.stable_ref for place in eligible_places}
        base_refs_by_day = {
            brief.day: [
                ref
                for ref in brief.allocated_selected_place_refs
                if ref not in source_refs
            ]
            for brief in draft.macro_plan.day_briefs
        }
        remaining_capacity: dict[int, dict[str, int]] = {}
        for day, refs in base_refs_by_day.items():
            used_meals = sum(
                1
                for ref in refs
                if ref in selected_by_ref
                and is_meal_place(
                    tags=selected_by_ref[ref].tags,
                    source_activity=selected_by_ref[ref].source_activity,
                )
            )
            used_activities = len(refs) - used_meals
            remaining_capacity[day] = {
                "activity": max(0, activity_capacity - used_activities),
                "meal": max(0, meal_capacity - used_meals),
            }
        latest_explicit_source_day = max(
            (
                place.source_day
                for place in eligible_places
                if place.source_day is not None
            ),
            default=0,
        )
        can_spill_explicit_source_days = (
            trip_days > latest_explicit_source_day
        )

        for place in eligible_places:
            slot_kind = (
                "meal"
                if is_meal_place(
                    tags=place.tags,
                    source_activity=place.source_activity,
                )
                else "activity"
            )
            if place.source_day is not None:
                if place.source_day > trip_days:
                    out_of_range.append(place)
                    continue
                assigned_day = place.source_day
                if (
                    remaining_capacity[assigned_day][slot_kind] <= 0
                    and can_spill_explicit_source_days
                ):
                    assigned_day = next(
                        (
                            day
                            for day in range(place.source_day + 1, trip_days + 1)
                            if remaining_capacity[day][slot_kind] > 0
                        ),
                        assigned_day,
                    )
                if remaining_capacity[assigned_day][slot_kind] <= 0:
                    over_capacity.append(place)
                    continue
                assigned_days[place.stable_ref] = assigned_day
                remaining_capacity[assigned_day][slot_kind] -= 1

        for place in eligible_places:
            if place.source_day is not None:
                continue
            slot_kind = (
                "meal"
                if is_meal_place(
                    tags=place.tags,
                    source_activity=place.source_activity,
                )
                else "activity"
            )
            assigned_day = next(
                (
                    day
                    for day in range(1, trip_days + 1)
                    if remaining_capacity[day][slot_kind] > 0
                ),
                None,
            )
            if assigned_day is None:
                over_capacity.append(place)
                continue
            assigned_days[place.stable_ref] = assigned_day
            remaining_capacity[assigned_day][slot_kind] -= 1

        refs_by_day: dict[int, list[str]] = {
            day: [] for day in range(1, trip_days + 1)
        }
        for place in eligible_places:
            assigned_day = assigned_days.get(place.stable_ref)
            if assigned_day is not None:
                refs_by_day[assigned_day].append(place.stable_ref)

        normalized_briefs = [
            brief.model_copy(
                update={
                    "allocated_selected_place_refs": [
                        *base_refs_by_day[brief.day],
                    ]
                    + refs_by_day[brief.day],
                    "notes": list(
                        dict.fromkeys(
                            [
                                *brief.notes,
                                *(
                                    [
                                        "URL itinerary order is preserved unless "
                                        "a hard constraint blocks a stop."
                                    ]
                                    if refs_by_day[brief.day]
                                    else []
                                ),
                            ]
                        )
                    ),
                }
            )
            for brief in draft.macro_plan.day_briefs
        ]
        out_of_range_refs = {place.stable_ref for place in out_of_range}
        normalized_unallocated = [
            item
            for item in draft.unallocated_selected_places
            if item.place.stable_ref not in source_refs
        ]
        normalized_unallocated.extend(
            UnallocatedSelectedPlace(
                place=selected_by_ref[place.stable_ref],
                reasonCode="source_day_out_of_range",
                reason=(
                    f"The URL assigns this stop to day {place.source_day}, "
                    f"outside the requested {trip_days}-day trip."
                ),
            )
            for place in out_of_range
            if place.stable_ref in out_of_range_refs
        )
        normalized_unallocated.extend(
            UnallocatedSelectedPlace(
                place=selected_by_ref[place.stable_ref],
                reasonCode="no_day_capacity",
                reason=(
                    f"Day {place.source_day} exceeds the available "
                    f"{'meal' if is_meal_place(tags=place.tags, source_activity=place.source_activity) else 'activity'} slots."
                    if place.source_day is not None
                    else (
                        f"The requested {trip_days}-day trip has no remaining "
                        "meal/activity capacity for this URL stop."
                    )
                ),
            )
            for place in over_capacity
        )
        return draft.model_copy(
            update={
                "macro_plan": draft.macro_plan.model_copy(
                    update={"day_briefs": normalized_briefs}
                ),
                "unallocated_selected_places": normalized_unallocated,
            }
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
