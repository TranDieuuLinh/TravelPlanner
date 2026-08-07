from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.knowledge_graph.research import (
    GraphScopeError,
    TripResearchBundle,
    TrustLevel,
)
from app.modules.plans.domain.entities import (
    RegionSnapshotReference,
    TravelIntent,
    TripThemeRequirement,
)
from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    TripThemePlanningInput,
    TripThemePlanningOutput,
    TripThemeDraft,
    PlanningAgentName,
    PlanningAgentStatus,
    PlanningIntent,
    PlanningMode,
    PlanWorkingState,
    RequiredExperience,
    RequiredExperienceSelectionPolicy,
    RegionStatisticsContext,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.trip_theme_planner.prompt import (
    TRIP_THEME_PROMPT_VERSION,
    TRIP_THEME_SYSTEM_PROMPT,
    build_theme_selection_policy,
    build_trip_theme_repair_payload,
    build_trip_theme_payload,
)
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    GraphCandidateCatalog,
    GraphExperienceCandidate,
    candidate_diversity_key,
    project_graph_candidate_catalog,
)
from app.modules.plans.trip_theme_planner.graph_research import (
    TripResearchOrchestrator,
    TripThemeGraphResearchService,
)
from app.modules.plans.trip_theme_planner.required_experience_validator import (
    RequiredExperienceGraphValidationError,
    validate as validate_trip_theme_output,
    validate_required_experience,
)
from app.modules.plans.trip_theme_planner.region_context import (
    PlannerStatisticsProvider,
    load_region_statistics_context,
)
from app.modules.plans.timing import PlanTimingSubstage
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
)

logger = logging.getLogger(__name__)
TRIP_THEME_MAX_REPAIR_ATTEMPTS = 3


def _record_timing_stage(
    callback: Callable[[PlanTimingSubstage], None] | None,
    key: str,
    label: str,
    started_at: float,
    *,
    details: dict[str, str | int | float | bool | None] | None = None,
) -> None:
    if callback is None:
        return
    callback(
        PlanTimingSubstage(
            key=key,
            label=label,
            durationSeconds=round(
                max(0.0, time.perf_counter() - started_at),
                4,
            ),
            details=details or {},
        )
    )


def _candidate_matches_requirement(
    requirement: RequiredExperience,
    candidate: GraphExperienceCandidate,
) -> bool:
    evidence = set(requirement.claim_ids)
    places = set(requirement.anchor_place_ids) | set(requirement.candidate_place_ids)
    return bool(
        evidence.intersection(candidate.claim_ids)
        or places.intersection(candidate.place_ids)
        or (
            requirement.activity_id is not None
            and requirement.activity_id == candidate.activity_id
        )
    )


def _candidate_priority(
    candidate: GraphExperienceCandidate,
    planner_input: TripThemePlanningInput,
) -> tuple[int, int, int, int, int, int]:
    """Order hard-filtered candidates by traveler signals before graph rank."""
    reasons = set(candidate.rank_reasons)
    interests = {value.casefold() for value in planner_input.intent.interests}
    profile_values = {
        value.casefold()
        for value in planner_input.preference_profile.top_values(
            dimensions=None,
        )
    }
    category = candidate.category.value.casefold()
    activity = (candidate.activity_name or "").casefold()
    current_match = int(category in interests or any(value in activity for value in interests))
    profile_match = int(category in profile_values or any(value in activity for value in profile_values))
    must_match = int("user_selected_place" in reasons or "source_place" in reasons or "must" in reasons)
    return (
        must_match,
        current_match,
        profile_match,
        int(candidate.is_special_experience),
        -candidate.rank,
        -len(candidate.place_ids),
    )


def _enforce_experience_diversity(
    requirements: list[RequiredExperience],
    catalog: GraphCandidateCatalog,
    planner_input: TripThemePlanningInput,
) -> tuple[list[RequiredExperience], list[str]]:
    """Keep graph-backed policies while preventing duplicate main experiences."""
    if not requirements or not catalog.candidates:
        return requirements, []

    candidates = sorted(
        catalog.candidates,
        key=lambda candidate: _candidate_priority(candidate, planner_input),
        reverse=True,
    )
    used_activities: set[str] = set()
    used_categories = set()
    selected: list[RequiredExperience] = []
    warnings: list[str] = []

    for requirement in requirements:
        matching = [
            candidate for candidate in candidates
            if _candidate_matches_requirement(requirement, candidate)
        ]
        if not matching:
            matching = candidates
        matching.sort(
            key=lambda candidate: (
                int(candidate.activity_id in used_activities if candidate.activity_id else False),
                int(candidate.category in used_categories),
                -_candidate_priority(candidate, planner_input)[0],
                candidate.rank,
            )
        )
        chosen = matching[0]
        for candidate in matching:
            activity_free = not candidate.activity_id or candidate.activity_id not in used_activities
            category_free = candidate.category not in used_categories
            if activity_free and category_free:
                chosen = candidate
                break

        policy = requirement.selection_policy
        if policy is RequiredExperienceSelectionPolicy.required_anchor:
            # An anchor is a user-visible hard choice; never silently replace it.
            anchored = next(
                (candidate for candidate in matching if set(requirement.anchor_place_ids) & set(candidate.anchor_place_ids)),
                None,
            )
            if anchored is not None:
                chosen = anchored

        updated = requirement.model_copy(
            update={
                "category": chosen.category,
                "activity_id": chosen.activity_id,
                "claim_ids": list(chosen.claim_ids),
                "evidence_claim_ids": list(chosen.claim_ids),
                "source_refs": list(chosen.source_refs),
                "anchor_place_ids": list(chosen.anchor_place_ids) if policy is RequiredExperienceSelectionPolicy.required_anchor else requirement.anchor_place_ids,
                "candidate_place_ids": list(chosen.candidate_place_ids) if policy is RequiredExperienceSelectionPolicy.choose_one else requirement.candidate_place_ids,
            }
        )
        selected.append(updated)
        if chosen.activity_id:
            used_activities.add(chosen.activity_id)
        used_categories.add(chosen.category)

    unique_keys = {candidate_diversity_key(candidate) for candidate in candidates}
    if len(unique_keys) < len(requirements) or len(used_activities) < sum(
        bool(requirement.activity_id) for requirement in selected
    ):
        warnings.append(
            "Catalog nhỏ hoặc thiếu candidate phù hợp nên không thể đạt đủ diversity "
            "theo activity/category; giữ lại các trải nghiệm hợp lệ tốt nhất."
        )
    non_food = [candidate for candidate in candidates if candidate.category.value not in {"food", "meal"}]
    if non_food and selected and all(
        requirement.category.value in {"food", "meal"} for requirement in selected
    ):
        replacement = next(
            (candidate for candidate in non_food if candidate.category not in used_categories),
            non_food[0],
        )
        replacement_index = next(
            (
                index for index in range(len(selected) - 1, -1, -1)
                if selected[index].selection_policy is not RequiredExperienceSelectionPolicy.required_anchor
            ),
            None,
        )
        if replacement_index is not None:
            original = selected[replacement_index]
            selected[replacement_index] = original.model_copy(
                update={
                    "category": replacement.category,
                    "activity_id": replacement.activity_id,
                    "claim_ids": list(replacement.claim_ids),
                    "evidence_claim_ids": list(replacement.claim_ids),
                    "source_refs": list(replacement.source_refs),
                    "candidate_place_ids": (
                        list(replacement.candidate_place_ids)
                        if original.selection_policy is RequiredExperienceSelectionPolicy.choose_one
                        else original.candidate_place_ids
                    ),
                    "anchor_place_ids": (
                        list(replacement.anchor_place_ids)
                        if original.selection_policy is RequiredExperienceSelectionPolicy.required_anchor
                        else original.anchor_place_ids
                    ),
                }
            )
        warnings.append(
            "Diversity hậu kiểm đã ưu tiên candidate ngoài food khi catalog có lựa chọn hợp lệ."
        )
    return selected, warnings


class TripThemePlannerService:
    def __init__(
        self,
        statistics_provider: PlannerStatisticsProvider,
        llm: LLMClient,
        graph_research_service: TripThemeGraphResearchService | None = None,
        graph_research_orchestrator: TripResearchOrchestrator | None = None,
        skip_statistics_for_explicit_intent: bool = False,
    ) -> None:
        self.statistics_provider = statistics_provider
        self.llm = llm
        self.skip_statistics_for_explicit_intent = (
            skip_statistics_for_explicit_intent
        )
        self.graph_research_service = (
            graph_research_service
            if graph_research_service is not None
            else (
                TripThemeGraphResearchService(graph_research_orchestrator)
                if graph_research_orchestrator is not None
                else None
            )
        )

    async def create_trip_themes(
        self,
        intent: TravelIntent,
        *,
        trip_spec: TripPlanningSpec,
        region_key: str,
        selected_places: list[SelectedPlaceContext],
        plan_state: PlanWorkingState | None = None,
        preference_profile: LongTermPreferenceProfile | None = None,
        on_timing_stage: Callable[[PlanTimingSubstage], None] | None = None,
    ) -> TripThemePlanningOutput:
        statistics_started = time.perf_counter()
        planner_input, statistics_status = self._build_input(
            mode=PlanningMode.main,
            intent=intent,
            trip_spec=trip_spec,
            region_key=region_key,
            selected_places=selected_places,
            plan_state=plan_state,
            preference_profile=preference_profile,
        )
        _record_timing_stage(
            on_timing_stage,
            "regionStatistics",
            "Tải thống kê catalog theo vùng",
            statistics_started,
            details={
                "status": statistics_status,
                "activePlaceCount": planner_input.region_context.active_place_count,
            },
        )
        return await self._create_plan(
            planner_input,
            statistics_status,
            preference_profile=preference_profile,
            on_timing_stage=on_timing_stage,
        )

    async def create_from_agent_input(
        self,
        planner_input: TripThemePlanningInput,
        *,
        on_timing_stage: Callable[[PlanTimingSubstage], None] | None = None,
    ) -> TripThemePlanningOutput:
        """Execute TripThemePlanner against an explicit evaluation contract."""
        return await self._create_plan(
            planner_input,
            "provided_evaluation_context",
            on_timing_stage=on_timing_stage,
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
        preference_profile: LongTermPreferenceProfile | None = None,
    ) -> tuple[TripThemePlanningInput, str]:
        has_explicit_theme_context = bool(
            intent.interests or intent.must_visit_places or selected_places
        )
        if self.skip_statistics_for_explicit_intent and has_explicit_theme_context:
            region_context = RegionStatisticsContext(
                regionKey=region_key,
                snapshotRef=RegionSnapshotReference(
                    regionKey=region_key,
                    snapshotId="intent-context",
                    catalogVersion=0,
                    algorithmVersion="intent_context_v1",
                    generatedAt=datetime.now(timezone.utc).isoformat(),
                ),
            )
            statistics_status = "skipped_explicit_intent"
        else:
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
            TripThemePlanningInput(
                mode=mode,
                intent=planning_intent,
                tripSpec=trip_spec,
                regionContext=region_context,
                selectedPlaces=selected_places,
                preferenceProfile=(
                    preference_profile or LongTermPreferenceProfile()
                ),
                planState=plan_state or PlanWorkingState(),
            ),
            statistics_status,
        )

    async def _create_plan(
        self,
        planner_input: TripThemePlanningInput,
        statistics_status: str,
        *,
        preference_profile: LongTermPreferenceProfile | None = None,
        on_timing_stage: Callable[[PlanTimingSubstage], None] | None = None,
    ) -> TripThemePlanningOutput:
        ready = (
            planner_input.region_context.active_place_count > 0
            or bool(planner_input.selected_places)
            or statistics_status == "skipped_explicit_intent"
        )
        statistics_warnings = self._statistics_warnings(planner_input)
        graph_catalog = GraphCandidateCatalog()
        graph_catalog_payload = graph_catalog.model_dump(mode="json", by_alias=True)
        graph_catalog_notes: list[str] = []
        graph_warnings: list[str] = []
        graph_research_blocked = False

        if self.graph_research_service is not None:
            graph_research_started = time.perf_counter()
            try:
                bundle = self.graph_research_service.research(
                    planner_input.intent,
                    planner_input.trip_spec,
                    planner_input.selected_places,
                    preference_profile or planner_input.preference_profile,
                )
            except GraphScopeError as exc:
                # Scope resolution failed — block the planner.
                # Redact the destination from logs per privacy rule.
                logger.warning(
                    "TripThemePlanner graph scope error: %s",
                    exc.CODE,
                )
                graph_research_blocked = True
                bundle = None
            except Exception:
                # Non-scope graph errors are caught generically.
                # Log only the error code to avoid recording full evidence/prompts.
                logger.warning(
                    "TripThemePlanner graph research failed: INTERNAL_ERROR"
                )
                graph_research_blocked = True
                bundle = None

            if bundle is not None and not isinstance(bundle, TripResearchBundle):
                bundle = None

            _record_timing_stage(
                on_timing_stage,
                "graphResearch",
                "Nghiên cứu Knowledge Graph",
                graph_research_started,
                details={
                    "status": "blocked" if graph_research_blocked else "completed",
                    "candidateCount": (
                        len(bundle.eligibleExperiences) if bundle is not None else 0
                    ),
                },
            )

            graph_projection_started = time.perf_counter()
            if bundle is not None:
                try:
                    graph_catalog = project_graph_candidate_catalog(bundle)
                except Exception:
                    logger.warning(
                        "TripThemePlanner graph candidate projection failed: "
                        "INTERNAL_ERROR"
                    )
                    graph_catalog = GraphCandidateCatalog()
                    graph_catalog_payload = graph_catalog.model_dump(
                        mode="json",
                        by_alias=True,
                    )
                    graph_research_blocked = True

                if graph_catalog.candidates:
                    graph_catalog_payload = graph_catalog.model_dump(
                        mode="json",
                        by_alias=True,
                    )
                    graph_catalog_notes.append(
                        f"graphCandidateCount={len(graph_catalog.candidates)}"
                    )
                    graph_catalog_notes.append(
                        f"graphScopeResultCount="
                        f"{len(bundle.scope.includedAreas) if bundle.scope else 0}"
                    )
                else:
                    graph_catalog_notes.append("graphCandidateCount=0")
                graph_warnings.extend(bundle.warnings)
            else:
                graph_catalog_notes.append("graphCandidateCount=0")
            _record_timing_stage(
                on_timing_stage,
                "graphProjection",
                "Chiếu graph evidence thành candidate catalog",
                graph_projection_started,
                details={
                    "candidateCount": len(graph_catalog.candidates),
                    "status": "blocked" if graph_research_blocked else "completed",
                },
            )
        else:
            graph_catalog_notes.append("graphCatalog=disabled")

        if graph_research_blocked:
            return TripThemePlanningOutput(
                mode=planner_input.mode,
                tripSpec=planner_input.trip_spec,
                tripThemesReady=False,
                warnings=statistics_warnings,
                trace=AgentTrace(
                    agent=PlanningAgentName.trip_theme_planner,
                    status=PlanningAgentStatus.blocked,
                    summary=(
                        "TripThemePlanner bị chặn: không thể phân giải phạm vi "
                        "địa lý từ knowledge graph cho điểm đến này."
                    ),
                    notes=[
                        "generator=llm",
                        f"promptVersion={TRIP_THEME_PROMPT_VERSION}",
                        *graph_catalog_notes,
                        (
                            "snapshotId="
                            f"{planner_input.region_context.snapshot_ref.snapshot_id}"
                        ),
                    ],
                ),
            )

        if not ready:
            return TripThemePlanningOutput(
                mode=planner_input.mode,
                tripSpec=planner_input.trip_spec,
                tripThemesReady=False,
                warnings=statistics_warnings,
                trace=AgentTrace(
                    agent=PlanningAgentName.trip_theme_planner,
                    status=PlanningAgentStatus.blocked,
                    summary=(
                        "Không có Place active hoặc địa điểm đã chọn để tạo "
                        "TripThemePlan."
                    ),
                    notes=[
                        "generator=llm",
                        f"promptVersion={TRIP_THEME_PROMPT_VERSION}",
                        *graph_catalog_notes,
                        (
                            "snapshotId="
                            f"{planner_input.region_context.snapshot_ref.snapshot_id}"
                        ),
                    ],
                ),
            )

        llm_started = time.perf_counter()
        try:
            raw = await self.llm.generate_structured_json(
                system_prompt=TRIP_THEME_SYSTEM_PROMPT,
                user_payload=build_trip_theme_payload(
                    planner_input,
                    graph_candidate_catalog=graph_catalog_payload,
                ),
                response_schema=TripThemeDraft.model_json_schema(),
            )
        except Exception:
            _record_timing_stage(
                on_timing_stage,
                "llmGenerate",
                "Gemini tạo TripThemeDraft",
                llm_started,
                details={"status": "failed"},
            )
            raise
        _record_timing_stage(
            on_timing_stage,
            "llmGenerate",
            "Gemini tạo TripThemeDraft",
            llm_started,
            details={
                "status": "completed",
                "responseCharacters": len(raw),
            },
        )
        repair_attempts = 0
        while True:
            validation_started = time.perf_counter()
            try:
                draft = self._parse_and_validate_theme_draft(
                    planner_input,
                    raw,
                    graph_catalog=graph_catalog,
                )
                _record_timing_stage(
                    on_timing_stage,
                    (
                        "validateThemeDraft"
                        if repair_attempts == 0
                        else f"validateThemeRepair{repair_attempts}"
                    ),
                    "Validate và chuẩn hóa TripThemeDraft",
                    validation_started,
                    details={
                        "status": "completed",
                        "attempt": repair_attempts,
                    },
                )
                break
            except (ValidationError, ValueError) as exc:
                _record_timing_stage(
                    on_timing_stage,
                    (
                        "validateThemeDraft"
                        if repair_attempts == 0
                        else f"validateThemeRepair{repair_attempts}"
                    ),
                    "Validate và chuẩn hóa TripThemeDraft",
                    validation_started,
                    details={
                        "status": "failed",
                        "attempt": repair_attempts,
                        "errorType": type(exc).__name__,
                    },
                )
                feedback = self._validation_feedback(exc)
                if repair_attempts >= TRIP_THEME_MAX_REPAIR_ATTEMPTS:
                    logger.warning(
                        "TripThemePlanner contract remained invalid "
                        "after %s repair attempts: %s",
                        repair_attempts,
                        feedback,
                    )
                    raise RuntimeError(
                        "LLM TripThemePlanner returned an invalid theme contract "
                        f"after {repair_attempts} repair attempts."
                    ) from exc

                repair_attempts += 1
                repair_started = time.perf_counter()
                try:
                    raw = await self.llm.generate_structured_json(
                        system_prompt=TRIP_THEME_SYSTEM_PROMPT,
                        user_payload=build_trip_theme_repair_payload(
                            planner_input,
                            previous_output=raw,
                            validation_feedback=feedback,
                            graph_candidate_catalog=graph_catalog_payload,
                        ),
                        response_schema=TripThemeDraft.model_json_schema(),
                    )
                except Exception:
                    _record_timing_stage(
                        on_timing_stage,
                        f"llmRepair{repair_attempts}",
                        "Gemini sửa TripThemeDraft không hợp lệ",
                        repair_started,
                        details={
                            "status": "failed",
                            "attempt": repair_attempts,
                        },
                    )
                    raise
                _record_timing_stage(
                    on_timing_stage,
                    f"llmRepair{repair_attempts}",
                    "Gemini sửa TripThemeDraft không hợp lệ",
                    repair_started,
                    details={
                        "status": "completed",
                        "attempt": repair_attempts,
                        "responseCharacters": len(raw),
                    },
                )

        warnings = list(
            dict.fromkeys(
                [
                    *draft.warnings,
                    *graph_warnings,
                    *statistics_warnings,
                ]
            )
        )
        return TripThemePlanningOutput(
            mode=planner_input.mode,
            tripSpec=planner_input.trip_spec,
            tripThemesReady=True,
            tripThemes=draft.trip_themes,
            requiredExperiences=draft.required_experiences,
            assumptions=draft.assumptions,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.trip_theme_planner,
                status=PlanningAgentStatus.completed,
                summary=(
                    "TripThemePlanner đã tạo yêu cầu trải nghiệm "
                    "toàn chuyến từ context và graph evidence."
                ),
                notes=[
                    "generator=llm",
                    f"repairAttempts={repair_attempts}",
                    f"promptVersion={TRIP_THEME_PROMPT_VERSION}",
                    f"statisticsStatus={statistics_status}",
                    *graph_catalog_notes,
                    (
                        "requiredExperienceCount="
                    f"{len(draft.required_experiences)}"
                    ),
                    (
                        "snapshotId="
                        f"{planner_input.region_context.snapshot_ref.snapshot_id}"
                    ),
                ],
            ),
        )

    def _parse_and_validate_theme_draft(
        self,
        planner_input: TripThemePlanningInput,
        raw: str,
        *,
        graph_catalog: GraphCandidateCatalog,
    ) -> TripThemeDraft:
        draft = TripThemeDraft.model_validate_json(raw)
        validation = validate_trip_theme_output(draft, graph_catalog)
        if not validation.is_valid:
            first = validation.errors[0]
            raise ValueError(
                f"{first.code}: {first.reason}"
                + (f" ({first.path})" if first.path else "")
            )
        if validation.output is not None:
            draft = validation.output
        if validation.warnings:
            draft = draft.model_copy(update={
                "warnings": [
                    *draft.warnings,
                    *[
                        f"{warning.code}: {warning.reason}"
                        for warning in validation.warnings
                    ],
                ]
            })
        themes, normalized = self._normalize_trip_themes(draft.trip_themes)
        allowed_region_prefixes = {
            planner_input.region_context.region_key,
            *(
                place.region_key
                for place in planner_input.selected_places
                if place.region_key
            ),
        }
        for requirement in themes:
            unknown_regions = {
                region_key
                for region_key in requirement.target_region_keys
                if not any(
                    region_key == prefix
                    or region_key.startswith(f"{prefix},")
                    for prefix in allowed_region_prefixes
                )
            }
            if unknown_regions:
                raise ValueError(
                    "Trip theme references an unknown targetRegionKey: "
                    f"{sorted(unknown_regions)[0]}"
                )

        required_experiences = list(draft.required_experiences)
        if required_experiences:
            try:
                required_experiences = [
                    validate_required_experience(requirement, graph_catalog)
                    for requirement in required_experiences
                ]
            except RequiredExperienceGraphValidationError as exc:
                raise ValueError(
                    "requiredExperiences references unsupported graph evidence: "
                    f"{exc}"
                ) from exc

        required_experiences, diversity_warnings = _enforce_experience_diversity(
            required_experiences,
            graph_catalog,
            planner_input,
        )

        selection_policy = build_theme_selection_policy(planner_input)
        required_count = min(
            int(selection_policy["minimumRequiredExperiences"]),
            len(graph_catalog.candidates),
        )
        if required_count and len(required_experiences) < required_count:
            raise ValueError(
                "requiredExperiences must contain at least "
                f"{required_count} graph candidates for this trip."
            )

        trusted_special_candidates = [
            candidate
            for candidate in graph_catalog.candidates
            if candidate.is_special_experience
            and candidate.trust is not TrustLevel.INFERRED
        ]
        if (
            selection_policy["selectionMode"]
            == "destination_special_experiences"
            and trusted_special_candidates
            and not required_experiences
        ):
            raise ValueError(
                "No trip intent, confirmed Place, or effective long-term "
                "profile was supplied; choose at least one trusted destination "
                "special experience from graphCandidateCatalog."
            )

        warnings = list(draft.warnings)
        warnings.extend(diversity_warnings)
        if normalized:
            warnings.append(
                "Tín hiệu trải nghiệm toàn chuyến đã được chuẩn hóa thành "
                "một pool đa dạng có giới hạn; điểm ăn uống được dành cho "
                "các khung bữa ăn riêng."
            )
        return draft.model_copy(
            update={
                "trip_themes": themes,
                "required_experiences": required_experiences,
                "warnings": warnings,
            }
        )

    @staticmethod
    def _normalize_trip_themes(
        themes: list[TripThemeRequirement],
    ) -> tuple[list[TripThemeRequirement], bool]:
        # Trip signals are stable when the solver changes the trip duration.
        # This is a bounded variety pool, not a per-day activity quota.
        capacity = 6
        remaining = capacity
        normalized: list[TripThemeRequirement] = []
        changed = False
        for requirement in themes:
            meal_theme_tags = {
                "food",
                "food_drink",
                "meal",
                "restaurant",
                "local food",
                "local cuisine",
            }
            meal_tags = [
                tag
                for tag in requirement.focus_tags
                if tag.casefold() in meal_theme_tags
                or is_meal_place(tags=[tag])
            ]
            non_meal_tags = [
                tag for tag in requirement.focus_tags if tag not in meal_tags
            ]
            if (meal_tags and not non_meal_tags) or (
                not requirement.focus_tags
                and is_meal_place(tags=[], source_activity=requirement.theme)
            ):
                changed = True
                continue
            if remaining <= 0:
                changed = True
                continue
            minimum = min(requirement.minimum_activities, remaining)
            focus_tags = non_meal_tags or requirement.focus_tags
            changed = changed or minimum != requirement.minimum_activities or (
                focus_tags != requirement.focus_tags
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
        return normalized, changed

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

    def _statistics_warnings(
        self,
        planner_input: TripThemePlanningInput,
    ) -> list[str]:
        context = planner_input.region_context
        warnings: list[str] = []
        if context.active_place_count == 0:
            if context.snapshot_ref.algorithm_version == "intent_context_v1":
                return warnings
            warnings.append(
                f"Không có Place active cho {context.region_key}; PlaceSelector chỉ "
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
                "Hơn một nửa Place active chưa có giờ mở cửa; PlaceSelector phải "
                "xác minh tính khả thi theo thời gian."
            )
        stale_data = int(eligible_quality.get("staleOperationalData", 0))
        if stale_data:
            warnings.append(
                f"{stale_data} Place active có dữ liệu vận hành đã cũ."
            )
        return warnings
