from app.integrations.llm.base import LLMClient
from app.modules.plans.domain.entities import (
    CheckReport,
    DayBrief,
    DayPartGoals,
    MacroPlan,
    TravelIntent,
)
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    AgentTrace,
    PlannerAgentInput,
    PlannerAgentOutput,
    PlanningAgentName,
    PlanningAgentStatus,
    PlanningIntent,
    PlanningMode,
    PlanWorkingState,
    SelectedPlaceContext,
    TripPlanningSpec,
    UnallocatedSelectedPlace,
)
from app.modules.plans.planner.prompt_builder import PlanPromptBuilder
from app.modules.plans.planner.region_context import (
    PlannerStatisticsProvider,
    load_region_statistics_context,
)


class PlannerService:
    def __init__(
        self,
        llm_client: LLMClient,
        statistics_provider: PlannerStatisticsProvider,
        prompt_builder: PlanPromptBuilder | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.statistics_provider = statistics_provider
        self.prompt_builder = prompt_builder or PlanPromptBuilder()

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
        await self.llm_client.generate_profile_plan(
            self.prompt_builder.build_prompt(planner_input)
        )
        macro_plan, unallocated = self._build_macro_plan(planner_input)
        warnings = self._statistics_warnings(planner_input)
        ready = planner_input.region_context.place_count > 0
        assumptions = [
            "Finder will choose exact places, times, and routes.",
            f"Region statistics status: {statistics_status}.",
        ]
        return PlannerAgentOutput(
            mode=planner_input.mode,
            macroPlan=AgentMacroPlan.model_validate(macro_plan.model_dump()),
            tripSpec=planner_input.trip_spec,
            dayBriefsReady=ready,
            unallocatedSelectedPlaces=unallocated,
            assumptions=assumptions,
            warnings=warnings,
            trace=AgentTrace(
                agent=PlanningAgentName.planner,
                status=(
                    PlanningAgentStatus.completed
                    if ready
                    else PlanningAgentStatus.blocked
                ),
                summary=(
                    "Created MacroPlan from the current region snapshot."
                    if ready
                    else "Region snapshot has no Places; DayBriefs need review."
                ),
                notes=[f"snapshotId={planner_input.region_context.snapshot_ref.snapshot_id}"],
            ),
        )

    def _build_macro_plan(
        self,
        planner_input: PlannerAgentInput,
    ) -> tuple[MacroPlan, list[UnallocatedSelectedPlace]]:
        intent = planner_input.intent
        context = planner_input.region_context
        dominant_tags = list(
            context.planner_signals.get("dominantTags", [])
        )
        focus = intent.interests or dominant_tags or ["local highlights"]
        candidate_areas = list(
            context.planner_signals.get("candidateAreas", [])
        )
        allocated_by_day: dict[int, list[str]] = {
            day: [] for day in range(1, planner_input.trip_spec.days + 1)
        }
        unallocated: list[UnallocatedSelectedPlace] = []
        excluded = {
            name.casefold()
            for name in planner_input.plan_state.excluded_place_names
        }
        selected_places = sorted(
            planner_input.selected_places,
            key=lambda place: (not place.must_visit, place.priority, place.name),
        )
        allocation_index = 0
        for place in selected_places:
            if place.name.casefold() in excluded:
                unallocated.append(
                    UnallocatedSelectedPlace(
                        place=place,
                        reasonCode="excluded_by_plan_state",
                        reason="Place is excluded from the current planning scope.",
                    )
                )
                continue
            day = allocation_index % planner_input.trip_spec.days + 1
            allocated_by_day[day].append(place.stable_ref)
            allocation_index += 1

        mode_label = planner_input.mode.value.title()
        briefs = [
            DayBrief(
                day=day,
                theme=(
                    f"{mode_label} day {day}: "
                    f"{focus[(day - 1) % len(focus)].replace('_', ' ').title()}"
                ),
                targetArea=self._target_area_name(
                    intent.destination,
                    candidate_areas,
                    day,
                ),
                targetRegionKey=self._target_region_key(
                    context.region_key,
                    candidate_areas,
                    day,
                ),
                focusTags=self._focus_tags(focus, dominant_tags, day),
                pace=intent.pace,
                dayPartGoals=self._day_part_goals(
                    focus[(day - 1) % len(focus)],
                    context.planner_signals,
                ),
                allocatedSelectedPlaceRefs=allocated_by_day[day],
                notes=[
                    f"Budget level: {intent.budget_level.value}",
                    "Exact schedule is delegated to Finder.",
                ],
            )
            for day in range(1, planner_input.trip_spec.days + 1)
        ]
        return (
            MacroPlan(
                title=f"{mode_label} plan for {intent.destination}",
                destination=intent.destination,
                regionKey=context.region_key,
                snapshotRef=context.snapshot_ref,
                dayBriefs=briefs,
            ),
            unallocated,
        )

    def _target_region_key(
        self,
        root_region_key: str,
        candidate_areas: list[dict],
        day: int,
    ) -> str:
        if not candidate_areas:
            return root_region_key
        area = candidate_areas[(day - 1) % len(candidate_areas)]
        return str(area.get("regionKey") or root_region_key)

    def _target_area_name(
        self,
        destination: str,
        candidate_areas: list[dict],
        day: int,
    ) -> str:
        region_key = self._target_region_key("", candidate_areas, day)
        if not region_key:
            return destination
        return region_key.split(",")[-1].replace("-", " ").title()

    def _focus_tags(
        self,
        focus: list[str],
        dominant_tags: list[str],
        day: int,
    ) -> list[str]:
        primary = focus[(day - 1) % len(focus)]
        return list(dict.fromkeys([primary, *dominant_tags[:2]]))

    def _day_part_goals(
        self,
        focus: str,
        planner_signals: dict,
    ) -> DayPartGoals:
        strong_parts = set(planner_signals.get("strongDayParts", []))
        weak_parts = set(planner_signals.get("weakDayParts", []))

        def goal(part: str) -> str:
            label = focus.replace("_", " ")
            if part in weak_parts:
                return f"Keep {part} flexible; regional data coverage is weak."
            if part in strong_parts:
                return f"Prioritize {label} activities supported in the {part}."
            return f"Use a balanced {label} block in the {part}."

        return DayPartGoals(
            morning=goal("morning"),
            lunch=goal("lunch"),
            afternoon=goal("afternoon"),
            evening=goal("evening"),
        )

    def _statistics_warnings(
        self,
        planner_input: PlannerAgentInput,
    ) -> list[str]:
        context = planner_input.region_context
        warnings: list[str] = []
        if context.place_count == 0:
            warnings.append(
                f"No Places are available for {context.region_key}."
            )
            return warnings
        missing_hours = int(context.data_quality.get("missingOpeningHours", 0))
        if missing_hours > context.place_count / 2:
            warnings.append(
                "More than half of regional Places have no opening-hours data; "
                "Finder must verify time feasibility."
            )
        stale_data = int(context.data_quality.get("staleOperationalData", 0))
        if stale_data:
            warnings.append(
                f"{stale_data} Places have stale operational data."
            )
        return warnings
