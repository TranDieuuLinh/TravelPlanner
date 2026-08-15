from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables


@dataclass(frozen=True, slots=True)
class InitialSolutionHint:
    selected_ids: frozenset[str]
    ordered_ids_by_day: dict[int, tuple[str, ...]]


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
    hinted_arcs = {
        (origin, destination, day)
        for day, ordered in hint.ordered_ids_by_day.items()
        for origin, destination in zip(ordered, ordered[1:], strict=False)
    }
    for key, arc in variables.arc.items():
        if key in hinted_arcs:
            model.AddHint(arc, 1)
