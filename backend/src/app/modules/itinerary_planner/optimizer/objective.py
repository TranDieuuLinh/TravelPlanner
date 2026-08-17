from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import CandidateSourceKind
from app.modules.itinerary_planner.optimizer.activity_coverage import (
    build_activity_coverage_value,
)
from app.modules.itinerary_planner.optimizer.config import ObjectiveWeights
from app.modules.itinerary_planner.optimizer.review_value import (
    build_popularity_value,
    build_quality_value,
)
from app.modules.itinerary_planner.optimizer.source_mix import build_source_mix_cost
from app.modules.itinerary_planner.optimizer.tag_diversity import (
    build_consecutive_tag_repetition_cost,
    build_same_day_tag_repetition_cost,
    meaningful_tags,
)
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.policies import (
    ACCOMMODATION_RELOCATION_DISTANCE_METERS,
    IDEAL_INTER_STOP_WAIT_MINUTES,
    LIGHT_INTER_STOP_WAIT_MINUTES,
    MEAL_POLICIES,
    STANDARD_DAY_END_MINUTE,
    STRONG_INTER_STOP_WAIT_MINUTES,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem


@dataclass(frozen=True, slots=True)
class ObjectiveExpressions:
    utility: cp_model.LinearExpr
    components: dict[str, cp_model.LinearExpr]


def build_objective(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    variables: PlannerVariables,
    weights: ObjectiveWeights,
) -> ObjectiveExpressions:
    positive = {
        "activityCoverageValue": build_activity_coverage_value(
            model, problem, variables, weights
        ),
        "specialExperienceValue": _special_value(problem, variables, weights),
        "preferenceValue": _preference_value(problem, variables, weights),
        "styleValue": _style_value(problem, variables, weights),
        "placeQualityValue": build_quality_value(problem, variables, weights),
        "popularityValue": build_popularity_value(problem, variables, weights),
        "timeFitValue": _time_fit(model, problem, variables, weights),
        "relationshipValue": _relationship_value(model, problem, variables, weights),
    }
    negative = {
        "sameDayTagRepetitionCost": build_same_day_tag_repetition_cost(
            model, problem, variables, weights.diversity_medium
        ),
        "consecutiveTagRepetitionCost": build_consecutive_tag_repetition_cost(
            problem, variables, weights.consecutive_diversity_max
        ),
        "foodDiversityCost": _food_diversity(model, problem, variables, weights),
        "travelTimeCost": _travel_cost(routing, variables, weights),
        "accommodationRelocationCost": _accommodation_relocation_cost(
            routing, variables, weights
        ),
        "accommodationPriceCost": _accommodation_price_cost(
            problem, variables, weights
        ),
        "idleWaitingCost": _waiting_cost(model, variables, weights),
        "mealDeviationCost": _meal_deviation(model, variables, weights),
        "fatigueCost": _fatigue(model, problem, variables, weights),
        "dayImbalanceCost": _day_imbalance(model, problem, variables, weights),
        "sourceMixDeviationCost": build_source_mix_cost(
            model, problem, variables, weights.source_mix_deviation
        ),
        "budgetOverageCost": (
            variables.budget_overage_units * weights.budget_overage_10k
            if variables.budget_overage_units is not None
            else 0
        ),
        "unknownOpeningCost": sum(
            variables.selected[candidate_id] * weights.unknown_opening
            for candidate_id in problem.unknown_opening_ids
            if candidate_id in variables.selected
        ),
    }
    utility = sum(positive.values()) - sum(negative.values())
    return ObjectiveExpressions(utility=utility, components={**positive, **negative})


def _special_value(problem, variables, weights):
    return sum(
        variables.selected[candidate_id] * weights.special_experience
        for candidate_id, candidate in problem.candidate_by_id.items()
        if candidate.source_kind
        in {CandidateSourceKind.special_experience, CandidateSourceKind.both}
    )


def _preference_value(problem, variables, weights):
    preferences = set(problem.trip.preferences.tags)
    if not preferences:
        return 0
    terms = []
    for candidate_id, candidate in problem.candidate_by_id.items():
        ratio = len(preferences & set(candidate.tags)) / len(preferences)
        terms.append(
            variables.selected[candidate_id] * round(ratio * weights.preference_max)
        )
    return sum(terms)


def _style_value(problem, variables, weights):
    styles = set(problem.trip.preferences.styles)
    if not styles:
        return 0
    return sum(
        variables.selected[candidate_id]
        * round(len(styles & set(candidate.styles)) / len(styles) * weights.style_max)
        for candidate_id, candidate in problem.candidate_by_id.items()
    )


def _time_fit(model, problem, variables, weights):
    values = []
    for candidate_id, preferred in problem.preferred_windows.items():
        if not preferred:
            continue
        for day in problem.feasible_days[candidate_id]:
            assigned = variables.assigned[(candidate_id, day)]
            day_matches = []
            for index, window in enumerate(preferred):
                full = variables.remember(
                    model.NewBoolVar(f"preferred_full:{candidate_id}:{day}:{index}")
                )
                partial = variables.remember(
                    model.NewBoolVar(f"preferred_partial:{candidate_id}:{day}:{index}")
                )
                model.Add(full <= assigned)
                model.Add(partial <= assigned)
                model.Add(
                    variables.start[(candidate_id, day)] >= window.start_minute
                ).OnlyEnforceIf(full)
                model.Add(
                    variables.end[(candidate_id, day)] <= window.end_minute
                ).OnlyEnforceIf(full)
                model.Add(
                    variables.start[(candidate_id, day)] < window.end_minute
                ).OnlyEnforceIf(partial)
                model.Add(
                    variables.end[(candidate_id, day)] > window.start_minute
                ).OnlyEnforceIf(partial)
                day_matches.extend((full, partial))
                values.extend(
                    (full * weights.time_fit, partial * (weights.time_fit // 2))
                )
            model.Add(sum(day_matches) <= assigned)
    return sum(values)


def _relationship_value(model, problem, variables, weights):
    same_day = []
    for origin_id, targets in problem.related_by_place.items():
        for destination_id in targets:
            common_days = (
                problem.feasible_days[origin_id] & problem.feasible_days[destination_id]
            )
            for day in common_days:
                related = variables.remember(
                    model.NewBoolVar(f"related:{origin_id}:{destination_id}:{day}")
                )
                origin = variables.assigned[(origin_id, day)]
                destination = variables.assigned[(destination_id, day)]
                model.Add(related <= origin)
                model.Add(related <= destination)
                model.Add(related >= origin + destination - 1)
                same_day.append(related)
    return sum(same_day) * weights.relationship


def _food_diversity(model, problem, variables, weights):
    tags = sorted(
        {tag for food in problem.valid_food for tag in meaningful_tags(food.tags)}
    )
    costs = []
    for tag in tags:
        literals = [
            variables.selected[food.place_id]
            for food in problem.valid_food
            if tag in meaningful_tags(food.tags)
        ]
        costs.extend(
            _convex_repeat(model, literals, weights.food_diversity, f"food:{tag}")
        )
    return sum(costs)


def _convex_repeat(model, literals, coefficient, name):
    if len(literals) < 2:
        return []
    count = model.NewIntVar(0, len(literals), f"count:{name}")
    model.Add(count == sum(literals))
    first = model.NewIntVar(0, len(literals), f"repeat1:{name}")
    second = model.NewIntVar(0, len(literals), f"repeat2:{name}")
    model.AddMaxEquality(first, [count - 1, 0])
    model.AddMaxEquality(second, [count - 2, 0])
    return [first * coefficient, second * coefficient]


def _travel_cost(routing, variables, weights):
    sparse_travel_by_pair = {
        (arc.origin_id, arc.destination_id): arc.travel for arc in routing.sparse_arcs
    }
    scheduled = sum(
        arc
        * sparse_travel_by_pair[(origin, destination)].safe_minutes
        * weights.travel_minute
        for (origin, destination, day), arc in variables.arc.items()
        if not origin.startswith("__") and not destination.startswith("__")
    )
    travel_by_pair = routing.travel_by_candidate_pair
    accommodation = sum(
        transfer
        * travel_by_pair[
            (accommodation_id, candidate_id)
            if direction == "start"
            else (candidate_id, accommodation_id)
        ].safe_minutes
        * weights.travel_minute
        for (
            accommodation_id,
            candidate_id,
            _day,
            direction,
        ), transfer in variables.accommodation_transfer.items()
    )
    return scheduled + accommodation


def _accommodation_relocation_cost(routing, variables, weights):
    travel_by_pair = routing.travel_by_candidate_pair
    return sum(
        transfer * weights.accommodation_long_transfer
        for (
            accommodation_id,
            candidate_id,
            _day,
            direction,
        ), transfer in variables.accommodation_transfer.items()
        if travel_by_pair[
            (accommodation_id, candidate_id)
            if direction == "start"
            else (candidate_id, accommodation_id)
        ].distance_meters
        > ACCOMMODATION_RELOCATION_DISTANCE_METERS
    )


def _accommodation_price_cost(problem, variables, weights):
    return sum(
        selected
        * (
            problem.accommodation_cost_per_person_by_id[accommodation_id]
            * problem.accommodation_nights
            // 10_000
        )
        * weights.accommodation_price_10k
        for accommodation_id, selected in variables.accommodation_selected.items()
    )


def _waiting_cost(model, variables, weights):
    costs = []
    for key, waiting in variables.waiting.items():
        light = _waiting_excess(
            model,
            variables,
            waiting,
            IDEAL_INTER_STOP_WAIT_MINUTES,
            f"light_wait:{key}",
        )
        strong = _waiting_excess(
            model,
            variables,
            waiting,
            LIGHT_INTER_STOP_WAIT_MINUTES,
            f"strong_wait:{key}",
        )
        very_strong = _waiting_excess(
            model,
            variables,
            waiting,
            STRONG_INTER_STOP_WAIT_MINUTES,
            f"very_strong_wait:{key}",
        )
        costs.extend(
            (
                light * weights.waiting_minute,
                strong * weights.waiting_minute * 2,
                very_strong * weights.waiting_minute * 6,
            )
        )
    return sum(costs)


def _waiting_excess(model, variables, waiting, threshold, name):
    value = variables.remember(model.NewIntVar(0, 1440, name))
    model.AddMaxEquality(value, [waiting - threshold, 0])
    return value


def _meal_deviation(model, variables, weights):
    deviations = []
    for (day, meal), start in variables.meal_start.items():
        deviation = variables.remember(
            model.NewIntVar(0, 1440, f"meal_deviation:{day}:{meal.value}")
        )
        model.AddAbsEquality(deviation, start - MEAL_POLICIES[meal].target_start)
        deviations.append(deviation)
    return sum(deviations) * weights.meal_deviation_minute


def _fatigue(model, problem, variables, weights):
    terms = []
    food_ids = {food.place_id for food in problem.valid_food}
    for day in range(1, problem.trip.days + 1):
        assignments = [
            variable
            for (candidate_id, candidate_day), variable in variables.assigned.items()
            if candidate_day == day
        ]
        stop_excess = variables.remember(
            model.NewIntVar(0, len(assignments), f"stop_excess:{day}")
        )
        model.AddMaxEquality(stop_excess, [sum(assignments) - 6, 0])
        terms.append(stop_excess * weights.excess_stop)
        active = sum(
            problem.candidate_by_id[candidate_id].duration_minutes * variable
            for (candidate_id, candidate_day), variable in variables.assigned.items()
            if candidate_day == day and candidate_id not in food_ids
        ) + sum(
            MEAL_POLICIES[meal].duration_minutes * variable
            for (food_id, meal_day, meal), variable in variables.meal.items()
            if meal_day == day
        )
        active_excess = variables.remember(
            model.NewIntVar(0, 1440, f"active_excess:{day}")
        )
        model.AddMaxEquality(active_excess, [active - 600, 0])
        terms.append(active_excess * weights.excess_active_minute)
        for (candidate_id, candidate_day), end in variables.end.items():
            if candidate_day != day:
                continue
            late = variables.remember(
                model.NewIntVar(0, 240, f"late_minutes:{candidate_id}:{day}")
            )
            model.AddMaxEquality(late, [end - STANDARD_DAY_END_MINUTE, 0])
            terms.append(late * weights.late_minute)
    return sum(terms)


def _day_imbalance(model, problem, variables, weights):
    totals = []
    food_ids = {food.place_id for food in problem.valid_food}
    for day in range(1, problem.trip.days + 1):
        total = variables.remember(model.NewIntVar(0, 1440, f"activity_minutes:{day}"))
        model.Add(
            total
            == sum(
                problem.candidate_by_id[candidate_id].duration_minutes * variable
                for (
                    candidate_id,
                    candidate_day,
                ), variable in variables.assigned.items()
                if candidate_day == day and candidate_id not in food_ids
            )
        )
        totals.append(total)
    maximum = variables.remember(model.NewIntVar(0, 1440, "max_activity_minutes"))
    minimum = variables.remember(model.NewIntVar(0, 1440, "min_activity_minutes"))
    model.AddMaxEquality(maximum, totals)
    model.AddMinEquality(minimum, totals)
    return (maximum - minimum) * weights.day_imbalance_minute
