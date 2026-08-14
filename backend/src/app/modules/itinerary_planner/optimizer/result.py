from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import MealType
from app.modules.itinerary_planner.optimizer.objective import ObjectiveExpressions
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


@dataclass(frozen=True, slots=True)
class ScheduledStop:
    place_id: str
    day: int
    start_minute: int
    end_minute: int
    meal_type: MealType | None


@dataclass(frozen=True, slots=True)
class SelectedRouteArc:
    origin_id: str
    destination_id: str
    day: int


@dataclass(frozen=True, slots=True)
class SelectedAccommodationTransfer:
    accommodation_id: str
    candidate_id: str
    day: int
    direction: str


@dataclass(frozen=True, slots=True)
class SolverPassResult:
    name: str
    status: str
    objective_value: int
    wall_time_ms: int
    optimality_proven: bool


@dataclass(frozen=True, slots=True)
class SourceMixPeriodResult:
    period: str
    target_special: int
    target_offer: int
    actual_special: int
    actual_offer: int

    @property
    def fallback_used(self) -> bool:
        return (
            self.actual_special != self.target_special
            or self.actual_offer != self.target_offer
        )


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    status: str
    optimality_proven: bool
    selected_ids: tuple[str, ...]
    scheduled_stops: tuple[ScheduledStop, ...]
    selected_arcs: tuple[SelectedRouteArc, ...]
    selected_accommodation_id: str | None
    accommodation_transfers: tuple[SelectedAccommodationTransfer, ...]
    total_cost_per_person: int
    user_input_count: int
    url_count: int
    objective_value: int
    objective_components: dict[str, int]
    objective_policy_version: str
    passes: tuple[SolverPassResult, ...]
    source_mix: tuple[SourceMixPeriodResult, ...]


def extract_result(
    solver: cp_model.CpSolver,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    objective: ObjectiveExpressions,
    objective_policy_version: str,
    passes: tuple[SolverPassResult, ...],
) -> OptimizationResult:
    selected_ids = tuple(
        candidate_id
        for candidate_id in sorted(variables.selected)
        if solver.Value(variables.selected[candidate_id])
    )
    meal_by_candidate_day = {
        (food_id, day): meal
        for (food_id, day, meal), variable in variables.meal.items()
        if solver.Value(variable)
    }
    stops = tuple(
        sorted(
            (
                ScheduledStop(
                    place_id=candidate_id,
                    day=day,
                    start_minute=solver.Value(variables.start[(candidate_id, day)]),
                    end_minute=solver.Value(variables.end[(candidate_id, day)]),
                    meal_type=meal_by_candidate_day.get((candidate_id, day)),
                )
                for (candidate_id, day), assigned in variables.assigned.items()
                if solver.Value(assigned)
            ),
            key=lambda stop: (stop.day, stop.start_minute, stop.place_id),
        )
    )
    selected_arc_keys = {
        key for key, variable in variables.arc.items() if solver.Value(variable)
    }
    ordered_arcs: list[SelectedRouteArc] = []
    for day in range(1, problem.trip.days + 1):
        outgoing = {
            origin: destination
            for origin, destination, arc_day in selected_arc_keys
            if arc_day == day
        }
        current = f"__start__:{day}"
        while current in outgoing:
            destination = outgoing[current]
            if not current.startswith("__") and not destination.startswith("__"):
                ordered_arcs.append(SelectedRouteArc(current, destination, day))
            current = destination
            if current == f"__end__:{day}":
                break
    arcs = tuple(ordered_arcs)
    selected_accommodation_id = next(
        (
            accommodation_id
            for accommodation_id, variable in variables.accommodation_selected.items()
            if solver.Value(variable)
        ),
        None,
    )
    accommodation_transfers = tuple(
        SelectedAccommodationTransfer(*key)
        for key, variable in sorted(variables.accommodation_transfer.items())
        if solver.Value(variable)
    )
    components = {
        name: solver.Value(expression)
        for name, expression in objective.components.items()
    }
    source_mix = tuple(
        _source_mix_period(solver, variables, period, target_special_tenths)
        for period, target_special_tenths in (("morning", 7), ("evening", 6))
    )
    return OptimizationResult(
        status=passes[-1].status,
        optimality_proven=all(item.optimality_proven for item in passes),
        selected_ids=selected_ids,
        scheduled_stops=stops,
        selected_arcs=arcs,
        selected_accommodation_id=selected_accommodation_id,
        accommodation_transfers=accommodation_transfers,
        total_cost_per_person=solver.Value(variables.total_cost),
        user_input_count=sum(
            solver.Value(variables.selected[candidate.place_id])
            for candidate in problem.candidate_by_id.values()
            if candidate.priority.value == "user_input"
        ),
        url_count=sum(
            solver.Value(variables.selected[candidate.place_id])
            for candidate in problem.candidate_by_id.values()
            if candidate.priority.value == "url"
        ),
        objective_value=solver.Value(objective.utility),
        objective_components=components,
        objective_policy_version=objective_policy_version,
        passes=passes,
        source_mix=source_mix,
    )


def _source_mix_period(
    solver: cp_model.CpSolver,
    variables: PlannerVariables,
    period: str,
    target_special_tenths: int,
) -> SourceMixPeriodResult:
    actual_special = sum(
        solver.Value(value)
        for key, value in variables.source_special.items()
        if key[2] == period
    )
    actual_offer = sum(
        solver.Value(value)
        for key, value in variables.source_offer.items()
        if key[2] == period
    )
    total = actual_special + actual_offer
    target_special = (total * target_special_tenths + 5) // 10
    return SourceMixPeriodResult(
        period=period,
        target_special=target_special,
        target_offer=total - target_special,
        actual_special=actual_special,
        actual_offer=actual_offer,
    )
