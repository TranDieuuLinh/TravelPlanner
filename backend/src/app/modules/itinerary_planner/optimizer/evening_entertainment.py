from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    CandidateSourceKind,
)
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.shared.tools.search_places.normalization import normalize_text

EVENING_START_MINUTE = 18 * 60
WATER_PUPPET_MARKERS = ("mua roi nuoc", "water puppet")


@dataclass(frozen=True, slots=True)
class EveningEntertainmentExpressions:
    special_value: cp_model.LinearExpr
    fallback_value: cp_model.LinearExpr
    special_conflict_cost: cp_model.LinearExpr


def build_evening_entertainment_policy(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    *,
    special_weight: int,
    fallback_weight: int,
    conflict_weight: int,
) -> EveningEntertainmentExpressions:
    special_ids = {
        item.place_id for item in problem.valid_places if _is_evening_special(item)
    }
    special_ids.update(
        item.place_id
        for item in problem.valid_entertainment
        if _is_water_puppet(item)
    )
    entertainment_ids = {
        item.place_id
        for item in problem.valid_entertainment
        if item.place_id not in special_ids
        and item.priority
        not in {CandidatePriority.user_input, CandidatePriority.url}
    }
    fallback_values = []
    special_values = []
    conflict_costs = []
    for day in range(1, problem.trip.days + 1):
        selected_entertainment = [
            variables.assigned[(candidate_id, day)]
            for candidate_id in entertainment_ids
            if (candidate_id, day) in variables.assigned
        ]
        evening_entertainment = _evening_indicators(
            model, variables, entertainment_ids, day, "entertainment"
        )
        evening_special = _evening_indicators(
            model, variables, special_ids, day, "special"
        )
        special_present = None
        if evening_special:
            special_present = variables.remember(
                model.NewBoolVar(f"evening_special_present:{day}")
            )
            model.AddMaxEquality(special_present, evening_special)
            special_values.append(special_present * special_weight)
        if not evening_entertainment:
            continue
        selected_present = variables.remember(
            model.NewBoolVar(f"optional_entertainment_present:{day}")
        )
        model.AddMaxEquality(selected_present, selected_entertainment)
        entertainment_present = variables.remember(
            model.NewBoolVar(f"evening_entertainment_present:{day}")
        )
        model.AddMaxEquality(entertainment_present, evening_entertainment)
        # Optional leisure (Entertainment or DrinkDessert) is useful in the
        # daytime only when the day also contains an evening fallback. This
        # moves the scarce slot to night instead of filling morning/afternoon.
        model.Add(selected_present <= entertainment_present)
        if special_present is not None:
            # A selected evening Special Experience (including water
            # puppetry) suppresses ordinary optional Entertainment that day.
            model.Add(selected_present + special_present <= 1)
            fallback = variables.remember(
                model.NewBoolVar(f"evening_entertainment_fallback:{day}")
            )
            model.Add(fallback <= entertainment_present)
            model.Add(fallback + special_present <= 1)
            model.Add(fallback >= entertainment_present - special_present)
            conflict = variables.remember(
                model.NewBoolVar(f"evening_entertainment_special_conflict:{day}")
            )
            model.Add(conflict <= entertainment_present)
            model.Add(conflict <= special_present)
            model.Add(conflict >= entertainment_present + special_present - 1)
            conflict_costs.append(conflict * conflict_weight)
        else:
            fallback = entertainment_present
        fallback_values.append(fallback * fallback_weight)
    return EveningEntertainmentExpressions(
        special_value=sum(special_values),
        fallback_value=sum(fallback_values),
        special_conflict_cost=sum(conflict_costs),
    )


def _evening_indicators(
    model: cp_model.CpModel,
    variables: PlannerVariables,
    candidate_ids: set[str],
    day: int,
    label: str,
) -> list[cp_model.IntVar]:
    indicators = []
    for candidate_id in candidate_ids:
        assigned = variables.assigned.get((candidate_id, day))
        if assigned is None:
            continue
        evening = variables.remember(
            model.NewBoolVar(f"evening_{label}:{candidate_id}:{day}")
        )
        model.Add(evening <= assigned)
        start = variables.start[(candidate_id, day)]
        model.Add(start >= EVENING_START_MINUTE).OnlyEnforceIf(evening)
        model.Add(start < EVENING_START_MINUTE).OnlyEnforceIf(
            [assigned, evening.Not()]
        )
        indicators.append(evening)
    return indicators


def _is_evening_special(candidate) -> bool:
    if candidate.source_kind in {
        CandidateSourceKind.special_experience,
        CandidateSourceKind.both,
    }:
        return True
    return _is_water_puppet(candidate)


def _is_water_puppet(candidate) -> bool:
    identity = normalize_text(" ".join([candidate.name, *candidate.tags]))
    return any(marker in identity for marker in WATER_PUPPET_MARKERS)
