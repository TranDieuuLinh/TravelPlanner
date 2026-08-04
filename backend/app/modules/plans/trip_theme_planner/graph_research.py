"""Map TripTheme context to the knowledge-graph research contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeAlias

from app.modules.knowledge_graph.research import (
    BudgetLevel as GraphBudgetLevel,
    TransportMode as GraphTransportMode,
    TravelBudget,
    TripResearchBundle,
    TripResearchInput,
)
from app.modules.plans.domain.entities import TravelIntent
from app.modules.plans.dto.agent_contracts import (
    PlanningIntent,
    SelectedPlaceContext,
    TransportMode,
    TripPlanningSpec,
)
from app.modules.preferences.schema import (
    LongTermPreferenceProfile,
    PreferenceDimension,
)


SelectedPlace: TypeAlias = SelectedPlaceContext | str
PlanningContextIntent: TypeAlias = PlanningIntent | TravelIntent


class TripResearchOrchestrator(Protocol):
    """The narrow orchestrator boundary used by the TripTheme adapter."""

    def research(self, input_data: TripResearchInput) -> TripResearchBundle:
        ...


_GRAPH_MODE_BY_PLANNER_MODE: dict[str, GraphTransportMode] = {
    TransportMode.walk.value: GraphTransportMode.WALKING,
    TransportMode.taxi.value: GraphTransportMode.TAXI,
    TransportMode.ride_hailing.value: GraphTransportMode.TAXI,
    TransportMode.bus.value: GraphTransportMode.PUBLIC_TRANSIT,
    TransportMode.train.value: GraphTransportMode.PUBLIC_TRANSIT,
    TransportMode.private_car.value: GraphTransportMode.CAR,
}

_PROFILE_INTEREST_DIMENSIONS = {
    PreferenceDimension.category,
    PreferenceDimension.attribute,
    PreferenceDimension.cuisine,
    PreferenceDimension.setting,
}


def build_trip_research_input(
    intent: PlanningContextIntent,
    trip_spec: TripPlanningSpec,
    selected_places: Sequence[SelectedPlace],
    preference_profile: LongTermPreferenceProfile | None = None,
) -> TripResearchInput:
    """Build a bounded graph-research input from normalized planning context.

    Only stable planning fields cross this boundary. In particular, selected
    places contribute their IDs rather than their notes or provider metadata.
    Profile values are reduced to normalized interest signals because the graph
    contract intentionally does not accept the profile document itself.
    """

    profile = preference_profile or LongTermPreferenceProfile()
    budget = trip_spec.budget

    return TripResearchInput(
        destination=intent.destination,
        destinationStays=[
            _destination_stay_name(stay)
            for stay in intent.destination_stays
        ],
        selectedPlaceIds=[
            place_id
            for place in selected_places
            if (place_id := _selected_place_id(place))
        ],
        interests=_merge_values(
            intent.interests,
            profile.top_values(
                dimensions=_PROFILE_INTEREST_DIMENSIONS,
            ),
        ),
        travelStyle=intent.travel_style,
        pace=_enum_value(intent.pace),
        days=trip_spec.days,
        partySize=trip_spec.party_size,
        startDate=trip_spec.start_date,
        endDate=trip_spec.end_date,
        budget=TravelBudget(
            level=GraphBudgetLevel(_enum_value(budget.level)),
            targetAmount=budget.target_amount,
            currency=budget.currency,
        ),
        constraints=list(intent.constraints),
        excludedPlaceTypes=list(
            intent.constraint_policy.excluded_place_types
        ),
        preferredModes=_map_transport_modes(
            trip_spec.transport.preferred_modes,
        ),
        avoidModes=_map_transport_modes(
            trip_spec.transport.avoid_modes,
        ),
    )


class TripThemeGraphResearchService:
    """Run graph research once for a normalized TripTheme context."""

    def __init__(self, orchestrator: TripResearchOrchestrator) -> None:
        self._orchestrator = orchestrator

    def research(
        self,
        intent: PlanningContextIntent,
        trip_spec: TripPlanningSpec,
        selected_places: Sequence[SelectedPlace],
        preference_profile: LongTermPreferenceProfile | None = None,
    ) -> TripResearchBundle:
        """Build the graph input and invoke the orchestrator exactly once."""

        research_input = build_trip_research_input(
            intent,
            trip_spec,
            selected_places,
            preference_profile,
        )
        return self._orchestrator.research(research_input)


def _destination_stay_name(stay: object) -> str:
    if isinstance(stay, str):
        return stay
    return str(getattr(stay, "name"))


def _selected_place_id(place: SelectedPlace) -> str | None:
    if isinstance(place, str):
        return place
    return place.place_id


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _merge_values(*groups: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for group in groups for value in group if value))


def _map_transport_modes(modes: Sequence[TransportMode]) -> list[GraphTransportMode]:
    return [
        mapped
        for mode in modes
        if (mapped := _GRAPH_MODE_BY_PLANNER_MODE.get(_enum_value(mode)))
    ]


__all__ = [
    "TripThemeGraphResearchService",
    "build_trip_research_input",
]
