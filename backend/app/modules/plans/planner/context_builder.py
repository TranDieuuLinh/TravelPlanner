from __future__ import annotations

from app.modules.plans.domain.entities import CheckReport, TravelIntent
from app.modules.plans.dto.agent_contracts import (
    AgentMacroPlan,
    PlannerAgentInput,
    PlanningIntent,
    PlanningMode,
    PlanWorkingState,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.planner.region_context import (
    PlannerStatisticsProvider,
    load_region_statistics_context,
)
from app.modules.preferences.schema import LongTermPreferenceProfile


class PlanningContextBuilder:
    """Build normalized Planner input without invoking research or generation."""

    def __init__(self, statistics_provider: PlannerStatisticsProvider) -> None:
        self.statistics_provider = statistics_provider

    def build(
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
