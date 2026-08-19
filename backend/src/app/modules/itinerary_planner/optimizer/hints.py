from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables


@dataclass(frozen=True, slots=True)
class InitialSolutionHint:
    selected_ids: frozenset[str]
    ordered_ids_by_day: dict[int, tuple[str, ...]]
    start_minutes: dict[tuple[str, int], int] | None = None
    meal_by_candidate_day: dict[tuple[str, int], str] | None = None
    accommodation_id: str | None = None


def hint_from_result(result: OptimizationResult) -> InitialSolutionHint:
    ordered: dict[int, list[str]] = {}
    starts: dict[tuple[str, int], int] = {}
    meals: dict[tuple[str, int], str] = {}
    for stop in sorted(
        result.scheduled_stops,
        key=lambda value: (value.day, value.start_minute, value.place_id),
    ):
        ordered.setdefault(stop.day, []).append(stop.place_id)
        starts[(stop.place_id, stop.day)] = stop.start_minute
        if stop.meal_type is not None:
            meals[(stop.place_id, stop.day)] = stop.meal_type.value
    return InitialSolutionHint(
        selected_ids=frozenset(result.selected_ids),
        ordered_ids_by_day={
            day: tuple(candidate_ids) for day, candidate_ids in ordered.items()
        },
        start_minutes=starts,
        meal_by_candidate_day=meals,
        accommodation_id=result.selected_accommodation_id,
    )


def apply_initial_hint(
    model: cp_model.CpModel,
    variables: PlannerVariables,
    hint: InitialSolutionHint,
) -> None:
    for candidate_id, selected in variables.selected.items():
        model.AddHint(selected, int(candidate_id in hint.selected_ids))
    for (candidate_id, day), assigned in variables.assigned.items():
        expected = candidate_id in hint.ordered_ids_by_day.get(day, ())
        model.AddHint(assigned, int(expected))
        if expected and hint.start_minutes is not None:
            start = hint.start_minutes.get((candidate_id, day))
            if start is not None:
                model.AddHint(variables.start[(candidate_id, day)], start)
    hinted_arcs = {
        (origin, destination, day)
        for day, ordered in hint.ordered_ids_by_day.items()
        for origin, destination in zip(ordered, ordered[1:], strict=False)
    }
    for key, arc in variables.arc.items():
        model.AddHint(arc, int(key in hinted_arcs))
    if hint.meal_by_candidate_day is not None:
        for (candidate_id, day, meal), variable in variables.meal.items():
            expected = hint.meal_by_candidate_day.get((candidate_id, day))
            model.AddHint(variable, int(expected == meal.value))
    if hint.accommodation_id is not None:
        for accommodation_id, variable in variables.accommodation_selected.items():
            model.AddHint(variable, int(accommodation_id == hint.accommodation_id))
