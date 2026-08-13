from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


@dataclass(frozen=True, slots=True)
class RepairLocks:
    baseline: OptimizationResult
    affected_days: frozenset[int]


def apply_repair_locks(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    locks: RepairLocks,
) -> None:
    stops = {
        (stop.place_id, stop.day): stop for stop in locks.baseline.scheduled_stops
    }
    selected_arcs = {
        (arc.origin_id, arc.destination_id, arc.day)
        for arc in locks.baseline.selected_arcs
    }
    for key, assigned in variables.assigned.items():
        _, day = key
        if day in locks.affected_days:
            continue
        stop = stops.get(key)
        model.Add(assigned == int(stop is not None))
        if stop is not None:
            model.Add(variables.start[key] == stop.start_minute)
            model.Add(variables.end[key] == stop.end_minute)

    for key, meal_variable in variables.meal.items():
        food_id, day, meal = key
        if day in locks.affected_days:
            continue
        stop = stops.get((food_id, day))
        model.Add(
            meal_variable == int(stop is not None and stop.meal_type == meal)
        )

    for key, arc in variables.arc.items():
        origin_id, destination_id, day = key
        if day in locks.affected_days:
            continue
        if origin_id.startswith("__") or destination_id.startswith("__"):
            continue
        model.Add(arc == int(key in selected_arcs))

    user_variables = [
        variables.selected[candidate.place_id]
        for candidate in problem.candidate_by_id.values()
        if candidate.priority.value == "user_input"
    ]
    url_variables = [
        variables.selected[candidate.place_id]
        for candidate in problem.candidate_by_id.values()
        if candidate.priority.value == "url"
    ]
    model.Add(sum(user_variables) == locks.baseline.user_input_count)
    model.Add(sum(url_variables) == locks.baseline.url_count)
