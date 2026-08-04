from __future__ import annotations

import logging

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import (
    TravelIntent,
    TripThemeRequirement,
)
from app.modules.plans.explorer.place_policy import is_meal_place
from app.modules.plans.dto.agent_contracts import (
    AgentTrace,
    TripThemePlanningInput,
    TripThemePlanningOutput,
    PlannerResearchDraft,
    TripThemeDraft,
    PlannerVerifiedResearch,
    PlanningAgentName,
    PlanningAgentStatus,
    PlanningIntent,
    PlanningMode,
    PlanWorkingState,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.trip_theme_planner.prompt import (
    TRIP_THEME_PROMPT_VERSION,
    TRIP_THEME_RESEARCH_PROMPT_VERSION,
    TRIP_THEME_RESEARCH_SYSTEM_PROMPT,
    TRIP_THEME_SYSTEM_PROMPT,
    build_trip_theme_repair_payload,
    build_trip_theme_research_payload,
    build_trip_theme_payload,
)
from app.modules.plans.trip_theme_planner.research_tool import (
    EmptyPlannerResearchTool,
    PlannerResearchTool,
)
from app.modules.plans.trip_theme_planner.region_context import (
    PlannerStatisticsProvider,
    load_region_statistics_context,
)
from app.modules.plans.trip_theme_planner.research_tools_orchestrator import ResearchToolsOrchestrator
from app.modules.plans.trip_theme_planner.research_tools_schema import (
    ConstraintResearchInput,
    FestivalDiscoveryInput,
    RegionOverviewInput,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
)

logger = logging.getLogger(__name__)
TRIP_THEME_MAX_REPAIR_ATTEMPTS = 3

CONSTRAINT_RADIUS_KM = 50.0


def _build_constraint_input(
    *,
    planner_input: TripThemePlanningInput,
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


class TripThemePlannerService:
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

    async def create_trip_themes(
        self,
        intent: TravelIntent,
        *,
        trip_spec: TripPlanningSpec,
        region_key: str,
        selected_places: list[SelectedPlaceContext],
        plan_state: PlanWorkingState | None = None,
        preference_profile: LongTermPreferenceProfile | None = None,
    ) -> TripThemePlanningOutput:
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

    async def create_from_agent_input(
        self,
        planner_input: TripThemePlanningInput,
    ) -> TripThemePlanningOutput:
        """Execute TripThemePlanner against an explicit evaluation contract."""
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
        preference_profile: LongTermPreferenceProfile | None = None,
    ) -> tuple[TripThemePlanningInput, str]:
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

    def _run_research_tools(
        self,
        planner_input: TripThemePlanningInput,
    ) -> TripThemePlanningInput:
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
        planner_input: TripThemePlanningInput,
        statistics_status: str,
    ) -> TripThemePlanningOutput:
        ready = (
            planner_input.region_context.active_place_count > 0
            or bool(planner_input.selected_places)
        )
        statistics_warnings = self._statistics_warnings(planner_input)
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
                system_prompt=TRIP_THEME_RESEARCH_SYSTEM_PROMPT,
                user_payload=build_trip_theme_research_payload(planner_input),
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
                "LLM TripThemePlanner returned an invalid research contract."
            ) from exc

        raw = await self.llm.generate_json(
            system_prompt=TRIP_THEME_SYSTEM_PROMPT,
            user_payload=build_trip_theme_payload(
                planner_input,
                research_draft,
                verified_research,
            ),
        )
        repair_attempts = 0
        while True:
            try:
                draft = self._parse_and_validate_theme_draft(
                    planner_input,
                    raw,
                    research_draft,
                    verified_research,
                )
                break
            except (ValidationError, ValueError) as exc:
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
                raw = await self.llm.generate_json(
                    system_prompt=TRIP_THEME_SYSTEM_PROMPT,
                    user_payload=build_trip_theme_repair_payload(
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
        return TripThemePlanningOutput(
            mode=planner_input.mode,
            tripSpec=planner_input.trip_spec,
            tripThemesReady=True,
            tripThemes=draft.trip_themes,
            assumptions=draft.assumptions,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.trip_theme_planner,
                status=PlanningAgentStatus.completed,
                summary=(
                    "TripThemePlanner đã tạo yêu cầu trải nghiệm "
                    "toàn chuyến từ context và thống kê khu vực."
                ),
                notes=[
                    "generator=llm",
                    f"repairAttempts={repair_attempts}",
                    f"researchPromptVersion={TRIP_THEME_RESEARCH_PROMPT_VERSION}",
                    f"promptVersion={TRIP_THEME_PROMPT_VERSION}",
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

    def _parse_and_validate_theme_draft(
        self,
        planner_input: TripThemePlanningInput,
        raw: str,
        research_draft: PlannerResearchDraft,
        verified_research: PlannerVerifiedResearch,
    ) -> TripThemeDraft:
        draft = TripThemeDraft.model_validate_json(raw)
        themes, normalized = self._normalize_trip_themes(
            draft.trip_themes,
            days=planner_input.trip_spec.days,
        )
        allowed_regions = {
            planner_input.region_context.region_key,
            *(region.region_key for region in verified_research.nearby_regions),
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
        for requirement in themes:
            unknown_regions = set(requirement.target_region_keys) - allowed_regions
            if unknown_regions:
                raise ValueError(
                    "Trip theme references an unknown targetRegionKey: "
                    f"{sorted(unknown_regions)[0]}"
                )
        warnings = list(draft.warnings)
        if normalized:
            warnings.append(
                "Yêu cầu chủ đề đã được chuẩn hóa theo sức chứa hai "
                "hoạt động chính mỗi ngày; điểm ăn uống được dành cho "
                "các khung bữa ăn riêng."
            )
        return draft.model_copy(
            update={"trip_themes": themes, "warnings": warnings}
        )

    @staticmethod
    def _normalize_trip_themes(
        themes: list[TripThemeRequirement],
        *,
        days: int,
    ) -> tuple[list[TripThemeRequirement], bool]:
        capacity = days * 2
        remaining = capacity
        normalized: list[TripThemeRequirement] = []
        changed = False
        for requirement in themes:
            meal_tags = [
                tag for tag in requirement.focus_tags if is_meal_place(tags=[tag])
            ]
            non_meal_tags = [
                tag for tag in requirement.focus_tags if not is_meal_place(tags=[tag])
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
