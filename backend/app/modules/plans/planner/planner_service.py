from __future__ import annotations

from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import (
    CheckReport,
    DayActivityNeed,
    DayBrief,
    DayMealNeed,
    MacroPlan,
    TravelIntent,
)
from app.modules.plans.domain.constraint_policy import constraint_policy_rejection
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    AgentTrace,
    PlannerAgentInput,
    PlannerAgentOutput,
    PlannerMacroPlanDraft,
    PlannerResearchDraft,
    PlannerVerifiedResearch,
    PlanningAgentName,
    PlanningAgentStatus,
    PlanningMode,
    PlanWorkingState,
    SelectedPlaceContext,
    TripPlanningSpec,
    UnallocatedSelectedPlace,
)
from app.modules.plans.planner.evidence import (
    PlannerEvidenceCollector,
)
from app.modules.plans.planner.context_builder import PlanningContextBuilder
from app.modules.plans.planner.generation import (
    MacroPlanGenerator,
)
from app.modules.plans.planner.prompt import (
    PLANNER_PROMPT_VERSION,
    PLANNER_RESEARCH_PROMPT_VERSION,
)
from app.modules.plans.planner.research_tool import (
    CAPABILITY_CATEGORY,
    PlannerResearchTool,
    canonical_capability,
)
from app.modules.plans.planner.tourism_zone_research import (
    TourismZoneResearchTool,
)
from app.modules.plans.planner.region_context import (
    PlannerStatisticsProvider,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceDimension,
)

class _PlannerOrchestrator:
    """Coordinate context, evidence and generation without owning policies."""
    def __init__(
        self,
        statistics_provider: PlannerStatisticsProvider,
        llm: LLMClient,
        research_tool: PlannerResearchTool | None = None,
        tourism_zone_tool: TourismZoneResearchTool | None = None,
        evidence_collector: PlannerEvidenceCollector | None = None,
        generator: MacroPlanGenerator | None = None,
        context_builder: PlanningContextBuilder | None = None,
    ) -> None:
        self.statistics_provider = statistics_provider
        self.context_builder = context_builder or PlanningContextBuilder(
            statistics_provider
        )
        self.evidence_collector = evidence_collector or PlannerEvidenceCollector(
            tourism_zone_tool=tourism_zone_tool,
        )
        self.generator = generator or MacroPlanGenerator(
            llm,
            research_tool,
        )
        # Compatibility aliases for existing runtime introspection. Execution
        # is owned by the composed collaborators above.
        self.llm = llm
        self.research_tool = self.generator.research_tool
        self.tourism_zone_tool = self.evidence_collector.tourism_zone_tool

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
        return self.context_builder.build(
            mode=mode,
            intent=intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            plan_state=plan_state,
            original_macro_plan=original_macro_plan,
            check_report=check_report,
            preference_profile=preference_profile,
        )

    async def _create_plan(
        self,
        planner_input: PlannerAgentInput,
        statistics_status: str,
    ) -> PlannerAgentOutput:
        evidence = self.evidence_collector.collect(planner_input)
        planner_input = evidence.apply_to(planner_input)
        ready = evidence.can_plan or bool(planner_input.selected_places)
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
                tourismZones=planner_input.tourism_zones,
                warnings=evidence.warnings,
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

        generation = await self.generator.generate(
            planner_input,
            evidence_payload=evidence.model_dump(mode="json", by_alias=True),
            validate_macro_draft=lambda raw, research, verified: (
                self._parse_and_validate_macro_draft(
                    planner_input,
                    raw,
                    research,
                    verified,
                )
            ),
        )
        draft = generation.draft
        verified_research = generation.verified_research

        warnings = list(
            dict.fromkeys(
                [
                    *draft.warnings,
                    *verified_research.warnings,
                    *evidence.warnings,
                ]
            )
        )
        return PlannerAgentOutput(
            mode=planner_input.mode,
            macroPlan=draft.macro_plan,
            tripSpec=planner_input.trip_spec,
            dayBriefsReady=True,
            tourismZones=planner_input.tourism_zones,
            unallocatedSelectedPlaces=draft.unallocated_selected_places,
            assumptions=draft.assumptions,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.planner,
                status=PlanningAgentStatus.completed,
                summary="AI đã tạo MacroPlan từ context và thống kê khu vực nhỏ.",
                notes=[
                    "generator=llm",
                    f"repairAttempts={generation.repair_attempts}",
                    f"researchPromptVersion={PLANNER_RESEARCH_PROMPT_VERSION}",
                    f"researchGenerator={generation.research_generator}",
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

class MacroPlanPolicy:
    """Validate and normalize a generated MacroPlan against verified evidence."""

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
            *(zone.region_key for zone in planner_input.tourism_zones),
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

        zone_by_id = {
            zone.zone_id: zone for zone in planner_input.tourism_zones
        }
        preferred_area_regions = list(
            dict.fromkeys(
                region_key
                for evidence in verified_research.experience_evidence
                if any(
                    node_id.startswith("area:")
                    for node_id in evidence.matched_node_ids
                )
                for region_key in evidence.region_keys
            )
        )
        preferred_area_zones = [
            zone
            for zone in planner_input.tourism_zones
            if self._region_matches_any(zone.region_key, preferred_area_regions)
        ]
        normalized_briefs = []
        for brief in macro.day_briefs:
            zone = None
            if brief.tourism_zone_ref is not None:
                zone = zone_by_id.get(brief.tourism_zone_ref)
                if zone is None:
                    raise ValueError(
                        f"Unknown tourismZoneRef: {brief.tourism_zone_ref}"
                    )
                if (
                    preferred_area_zones
                    and zone not in preferred_area_zones
                ):
                    # The model may choose a more popular zone even when the
                    # user's wording names a graph-known visitor area. Treat
                    # that area edge as a hard geographic scope and let the
                    # category selector choose an anchor inside it.
                    zone = None
            if zone is None and planner_input.tourism_zones:
                regional_zones = [
                    candidate
                    for candidate in planner_input.tourism_zones
                    if candidate.region_key == brief.target_region_key
                ]
                candidate_zones = (
                    preferred_area_zones
                    or regional_zones
                    or planner_input.tourism_zones
                )
                available_categories = list(
                    dict.fromkeys(
                        category
                        for candidate in candidate_zones
                        for category in candidate.primary_categories
                    )
                )
                preferred_category = self._primary_category_for_day(
                    planner_input,
                    brief,
                    available_categories,
                )
                zone = next(
                    (
                        candidate
                        for candidate in candidate_zones
                        if preferred_category in candidate.primary_categories
                    ),
                    candidate_zones[0],
                )

            focus_category = self._focus_category_for_day(
                brief,
                list(
                    dict.fromkeys(
                        category
                        for candidate in planner_input.tourism_zones
                        for category in candidate.primary_categories
                    )
                ),
            )
            if zone is not None and focus_category is not None:
                focus_zone_pool = preferred_area_zones or planner_input.tourism_zones
                matching_zone = next(
                    (
                        candidate
                        for candidate in focus_zone_pool
                        if candidate.region_key == zone.region_key
                        and focus_category in candidate.primary_categories
                    ),
                    None,
                )
                if matching_zone is None:
                    matching_zone = next(
                        (
                            candidate
                            for candidate in focus_zone_pool
                            if focus_category in candidate.primary_categories
                        ),
                        None,
                    )
                if matching_zone is not None:
                    zone = matching_zone

            updates = {}
            activity_needs = (
                brief.activity_needs
                if brief.activity_needs
                else self._default_activity_needs(brief)
            )
            normalized_activity_needs = self._normalize_activity_needs(
                activity_needs
            )
            if normalized_activity_needs != brief.activity_needs:
                updates["activity_needs"] = normalized_activity_needs
            if not brief.meal_needs:
                updates["meal_needs"] = [
                    DayMealNeed(
                        role="breakfast",
                        earliestStart="07:00",
                        latestEnd="09:00",
                        minDurationMinutes=30,
                        maxDurationMinutes=60,
                    ),
                    DayMealNeed(
                        role="lunch",
                        earliestStart="11:30",
                        latestEnd="13:30",
                        minDurationMinutes=45,
                        maxDurationMinutes=75,
                    ),
                    DayMealNeed(
                        role="dinner",
                        earliestStart="17:30",
                        latestEnd="20:00",
                        minDurationMinutes=45,
                        maxDurationMinutes=90,
                    ),
                ]
            if zone is not None:
                updates["tourism_zone_ref"] = zone.zone_id
                updates["target_region_key"] = zone.region_key
                updates["allow_region_fallback"] = False
                updates["main_region_locked"] = bool(preferred_area_zones)
                updates["anchor_place_refs"] = [
                    anchor.place_id for anchor in zone.anchor_places
                ]
                updates["primary_activity_category"] = (
                    focus_category
                    or self._primary_category_for_day(
                        planner_input,
                        brief,
                        zone.primary_categories,
                    )
                )
            normalized_brief = (
                brief.model_copy(update=updates) if updates else brief
            )
            if zone is not None and normalized_brief.primary_activity_category:
                supported_categories = set(zone.primary_categories) or {
                    anchor.category for anchor in zone.anchor_places
                }
                if (
                    supported_categories
                    and normalized_brief.primary_activity_category
                    not in supported_categories
                ):
                    raise ValueError(
                        "tourismZoneRef does not support "
                        "primaryActivityCategory."
                    )
            normalized_briefs.append(normalized_brief)
        if normalized_briefs != macro.day_briefs:
            macro = macro.model_copy(update={"day_briefs": normalized_briefs})
            draft = draft.model_copy(update={"macro_plan": macro})

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

    def _enforce_day_activity_capacity(
        self,
        planner_input: PlannerAgentInput,
        draft: PlannerMacroPlanDraft,
        *,
        selected_by_ref: dict[str, SelectedPlaceContext],
    ) -> PlannerMacroPlanDraft:
        capacity = 2
        overflow_refs: list[str] = []
        normalized_briefs = []
        for brief in draft.macro_plan.day_briefs:
            allocated = brief.allocated_selected_place_refs
            overflow_refs.extend(allocated[capacity:])
            normalized_briefs.append(
                brief.model_copy(
                    update={
                        "allocated_selected_place_refs": allocated[:capacity]
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
                    f"The current day frame allows at most {capacity} "
                    "activities per day."
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
        remaining_capacity = {
            day: max(0, activity_capacity - len(refs))
            for day, refs in base_refs_by_day.items()
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
            if place.source_day is not None:
                if place.source_day > trip_days:
                    out_of_range.append(place)
                    continue
                assigned_day = place.source_day
                if (
                    remaining_capacity[assigned_day] <= 0
                    and can_spill_explicit_source_days
                ):
                    assigned_day = next(
                        (
                            day
                            for day in range(place.source_day + 1, trip_days + 1)
                            if remaining_capacity[day] > 0
                        ),
                        assigned_day,
                    )
                if remaining_capacity[assigned_day] <= 0:
                    over_capacity.append(place)
                    continue
                assigned_days[place.stable_ref] = assigned_day
                remaining_capacity[assigned_day] -= 1

        for place in eligible_places:
            if place.source_day is not None:
                continue
            assigned_day = next(
                (
                    day
                    for day in range(1, trip_days + 1)
                    if remaining_capacity[day] > 0
                ),
                None,
            )
            if assigned_day is None:
                over_capacity.append(place)
                continue
            assigned_days[place.stable_ref] = assigned_day
            remaining_capacity[assigned_day] -= 1

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
                    f"Day {place.source_day} exceeds the "
                    f"current {activity_capacity}-activity day capacity."
                    if place.source_day is not None
                    else (
                        f"The requested {trip_days}-day trip has no remaining "
                        "activity capacity for this URL stop."
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

    @staticmethod
    def _focus_category_for_day(
        brief: DayBrief,
        available_categories: list[str],
    ) -> str | None:
        scores: dict[str, int] = {}
        weighted_signals = [
            (brief.day_part_goals.morning, 3),
            (brief.day_part_goals.afternoon, 3),
            *[(tag, 2) for tag in brief.focus_tags],
            (brief.theme, 2),
        ]
        for signal, weight in weighted_signals:
            if not signal:
                continue
            category = CAPABILITY_CATEGORY.get(
                canonical_capability(signal)
            )
            if category in available_categories:
                scores[category] = scores.get(category, 0) + weight
        if not scores:
            return None
        return max(
            scores,
            key=lambda category: (
                scores[category],
                category != "food_drink",
                category,
            ),
        )

    @staticmethod
    def _default_activity_needs(brief: DayBrief) -> list[DayActivityNeed]:
        common_experiences = list(dict.fromkeys(brief.focus_tags))
        main_experience = common_experiences[0] if common_experiences else None
        return [
            DayActivityNeed(
                role="main",
                goal=brief.day_part_goals.morning or brief.theme,
                experienceType=main_experience,
                preferredExperiences=common_experiences,
                minDurationMinutes=75,
                maxDurationMinutes=150,
                required=True,
                mustBeExactPlace=True,
            ),
            DayActivityNeed(
                role="support",
                goal=brief.day_part_goals.afternoon or brief.theme,
                preferredExperiences=common_experiences,
                minDurationMinutes=45,
                maxDurationMinutes=120,
                required=True,
            ),
            DayActivityNeed(
                role="bonus",
                goal=brief.day_part_goals.evening or brief.theme,
                preferredExperiences=common_experiences,
                minDurationMinutes=30,
                maxDurationMinutes=90,
                required=False,
            ),
        ]

    @staticmethod
    def _normalize_activity_needs(
        needs: list[DayActivityNeed],
    ) -> list[DayActivityNeed]:
        main_needs = [need for need in needs if need.role == "main"]
        if len(main_needs) != 1:
            raise ValueError(
                "Each DayBrief must contain exactly one required main experience."
            )
        normalized: list[DayActivityNeed] = []
        for need in needs:
            if need.role != "main":
                normalized.append(need)
                continue
            experience_type = need.experience_type or next(
                iter(need.preferred_experiences),
                None,
            )
            normalized.append(
                need.model_copy(
                    update={
                        "experience_type": experience_type,
                        "required": True,
                        "must_be_exact_place": True,
                    }
                )
            )
        return normalized

    @staticmethod
    def _region_matches_any(
        region_key: str,
        preferred_region_keys: list[str],
    ) -> bool:
        return any(
            region_key == preferred
            or region_key.startswith(f"{preferred},")
            or preferred.startswith(f"{region_key},")
            for preferred in preferred_region_keys
        )

    @staticmethod
    def _primary_category_for_day(
        planner_input: PlannerAgentInput,
        brief: DayBrief,
        available_categories: list[str],
    ) -> str | None:
        day_requested = [
            CAPABILITY_CATEGORY.get(canonical_capability(tag))
            for tag in brief.focus_tags
        ]
        requested = [
            CAPABILITY_CATEGORY.get(canonical_capability(interest))
            for interest in planner_input.intent.interests
        ]
        for category in (*day_requested, *requested):
            if category in available_categories:
                return category
        for category in (
            "attraction",
            "nature",
            "shopping",
            "entertainment",
            "food_drink",
        ):
            if category in available_categories:
                return category
        return None

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


class PlannerService(_PlannerOrchestrator, MacroPlanPolicy):
    """Public Planner facade preserving the existing workflow contract."""

    pass
