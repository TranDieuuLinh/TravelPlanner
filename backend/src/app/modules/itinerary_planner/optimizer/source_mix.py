from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import CandidateSourceKind
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


MORNING_END_MINUTE = 12 * 60
EVENING_START_MINUTE = 18 * 60
TARGET_SPECIAL_TENTHS = {"morning": 7, "evening": 6}


def build_source_mix_cost(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    weight: int,
) -> cp_model.LinearExpr:
    food_ids = {food.place_id for food in problem.valid_food}
    for (candidate_id, day), assigned in variables.assigned.items():
        if candidate_id in food_ids:
            continue
        candidate = problem.candidate_by_id[candidate_id]
        if candidate.source_kind == CandidateSourceKind.generic:
            continue
        for period in ("morning", "evening"):
            key = (candidate_id, day, period)
            indicator = _period_indicator(
                model, variables, key, assigned, period
            )
            variables.source_period[key] = indicator
            _assign_source(model, variables, key, indicator, candidate.source_kind)

    costs: list[cp_model.LinearExpr] = []
    for period, target_special in TARGET_SPECIAL_TENTHS.items():
        period_values = [
            value
            for key, value in variables.source_period.items()
            if key[2] == period
        ]
        if not period_values:
            continue
        special_values = [
            value
            for key, value in variables.source_special.items()
            if key[2] == period
        ]
        maximum = len(period_values)
        special_capacity, offer_capacity = _period_capacities(problem, period)
        total = variables.remember(
            model.NewIntVar(0, maximum, f"source_mix_total:{period}")
        )
        model.Add(total == sum(period_values))
        special = sum(special_values)
        target = variables.remember(
            model.NewIntVar(0, maximum, f"source_mix_target:{period}")
        )
        model.AddAllowedAssignments(
            [total, target],
            [
                (
                    count,
                    _feasible_special_target(
                        count,
                        target_special,
                        special_capacity,
                        offer_capacity,
                    ),
                )
                for count in range(maximum + 1)
            ],
        )
        deviation = variables.remember(
            model.NewIntVar(0, maximum, f"source_mix_deviation:{period}")
        )
        model.AddAbsEquality(deviation, special - target)
        costs.append(deviation * weight)
    return sum(costs)


def _period_capacities(
    problem: PreparedPlanningProblem, period: str
) -> tuple[int, int]:
    special = 0
    offer = 0
    for candidate in problem.valid_places:
        if not _can_fit_period(problem, candidate.place_id, period):
            continue
        if candidate.source_kind in {
            CandidateSourceKind.special_experience,
            CandidateSourceKind.both,
        }:
            special += 1
        if candidate.source_kind in {
            CandidateSourceKind.offer_item,
            CandidateSourceKind.both,
        }:
            offer += 1
    return special, offer


def _can_fit_period(
    problem: PreparedPlanningProblem, candidate_id: str, period: str
) -> bool:
    duration = problem.candidate_by_id[candidate_id].duration_minutes
    for day in problem.feasible_days[candidate_id]:
        for window in problem.feasible_windows[(candidate_id, day)]:
            if period == "morning":
                if window.start_minute + duration <= min(
                    window.end_minute, MORNING_END_MINUTE
                ):
                    return True
            elif (
                max(window.start_minute, EVENING_START_MINUTE) + duration
                <= window.end_minute
            ):
                return True
    return False


def _feasible_special_target(
    total: int,
    target_special_tenths: int,
    special_capacity: int,
    offer_capacity: int,
) -> int:
    requested = (total * target_special_tenths + 5) // 10
    minimum = max(0, total - offer_capacity)
    maximum = min(total, special_capacity)
    return min(max(requested, minimum), maximum)


def _period_indicator(
    model: cp_model.CpModel,
    variables: PlannerVariables,
    key: tuple[str, int, str],
    assigned: cp_model.IntVar,
    period: str,
) -> cp_model.IntVar:
    candidate_id, day, _ = key
    indicator = variables.remember(
        model.NewBoolVar(f"source_period:{period}:{candidate_id}:{day}")
    )
    model.Add(indicator <= assigned)
    if period == "morning":
        end = variables.end[(candidate_id, day)]
        model.Add(end <= MORNING_END_MINUTE).OnlyEnforceIf(indicator)
        model.Add(end > MORNING_END_MINUTE).OnlyEnforceIf(
            [assigned, indicator.Not()]
        )
    else:
        start = variables.start[(candidate_id, day)]
        model.Add(start >= EVENING_START_MINUTE).OnlyEnforceIf(indicator)
        model.Add(start < EVENING_START_MINUTE).OnlyEnforceIf(
            [assigned, indicator.Not()]
        )
    return indicator


def _assign_source(
    model: cp_model.CpModel,
    variables: PlannerVariables,
    key: tuple[str, int, str],
    indicator: cp_model.IntVar,
    source_kind: CandidateSourceKind,
) -> None:
    if source_kind == CandidateSourceKind.special_experience:
        variables.source_special[key] = indicator
        return
    if source_kind == CandidateSourceKind.offer_item:
        variables.source_offer[key] = indicator
        return
    special = variables.remember(
        model.NewBoolVar(f"source_special:{key[2]}:{key[0]}:{key[1]}")
    )
    offer = variables.remember(
        model.NewBoolVar(f"source_offer:{key[2]}:{key[0]}:{key[1]}")
    )
    model.Add(special + offer == indicator)
    variables.source_special[key] = special
    variables.source_offer[key] = offer
