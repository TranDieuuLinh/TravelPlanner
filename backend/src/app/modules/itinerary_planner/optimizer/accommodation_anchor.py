from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.policies import (
    ITINERARY_START_MINUTE,
    MINIMUM_OVERNIGHT_REST_MINUTES,
    OVERNIGHT_END_MINUTE,
)
from app.modules.itinerary_planner.routing_models import RoutingProblem


@dataclass(frozen=True, slots=True)
class DailyAccommodationAnchor:
    """Fixed hotel context used by one hybrid daily CP-SAT repair."""

    accommodation_id: str
    trip_day: int
    trip_days: int
    previous_last_end: int | None = None
    previous_return_minutes: int = 0

    @property
    def requires_start_transfer(self) -> bool:
        return self.trip_day > 1

    @property
    def requires_end_transfer(self) -> bool:
        return self.trip_day < self.trip_days


def add_daily_anchor_transfer(
    model: cp_model.CpModel,
    routing: RoutingProblem,
    variables: PlannerVariables,
    anchor: DailyAccommodationAnchor,
    *,
    candidate_id: str,
    direction: str,
    endpoint_arc: cp_model.IntVar,
) -> None:
    pair = (
        (anchor.accommodation_id, candidate_id)
        if direction == "start"
        else (candidate_id, anchor.accommodation_id)
    )
    travel = routing.travel_by_candidate_pair.get(pair)
    if travel is None:
        model.Add(endpoint_arc == 0)
        return
    if direction == "end":
        model.Add(
            variables.end[(candidate_id, 1)] + travel.safe_minutes
            <= OVERNIGHT_END_MINUTE
        ).OnlyEnforceIf(endpoint_arc)
        return

    minimum_start = ITINERARY_START_MINUTE + travel.safe_minutes
    if anchor.previous_last_end is not None:
        minimum_start = max(
            minimum_start,
            anchor.previous_last_end
            + anchor.previous_return_minutes
            + MINIMUM_OVERNIGHT_REST_MINUTES
            + travel.safe_minutes
            - 1440,
        )
    model.Add(
        variables.start[(candidate_id, 1)] >= minimum_start
    ).OnlyEnforceIf(endpoint_arc)
