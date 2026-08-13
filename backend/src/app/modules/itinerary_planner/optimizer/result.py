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
class SolverPassResult:
    name: str
    status: str
    objective_value: int
    wall_time_ms: int
    optimality_proven: bool


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    status: str
    optimality_proven: bool
    selected_ids: tuple[str, ...]
    scheduled_stops: tuple[ScheduledStop, ...]
    selected_arcs: tuple[SelectedRouteArc, ...]
    total_cost_per_person: int
    user_input_count: int
    url_count: int
    objective_value: int
    objective_components: dict[str, int]
    objective_policy_version: str
    passes: tuple[SolverPassResult, ...]


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
    components = {
        name: solver.Value(expression)
        for name, expression in objective.components.items()
    }
    return OptimizationResult(
        status=passes[-1].status,
        optimality_proven=all(item.optimality_proven for item in passes),
        selected_ids=selected_ids,
        scheduled_stops=stops,
        selected_arcs=arcs,
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
    )
