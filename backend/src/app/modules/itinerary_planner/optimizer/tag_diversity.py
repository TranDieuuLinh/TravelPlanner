from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem


IGNORED_TAG_PREFIXES = (
    "experience_special_experience",
    "food_item_",
    "item_",
    "pool_category_",
    "relationship_",
    "retrieval_",
    "style_",
)


def meaningful_tags(values: list[str]) -> frozenset[str]:
    return frozenset(
        value
        for value in values
        if value
        and value not in {"travel_place", "travelplace"}
        and not value.startswith(IGNORED_TAG_PREFIXES)
    )


def build_same_day_tag_repetition_cost(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    coefficient: int,
) -> cp_model.LinearExpr:
    candidates = problem.valid_places
    tags = sorted({tag for item in candidates for tag in meaningful_tags(item.tags)})
    costs = []
    for tag in tags:
        for day in range(1, problem.trip.days + 1):
            literals = [
                variables.assigned[(candidate.place_id, day)]
                for candidate in candidates
                if tag in meaningful_tags(candidate.tags)
                and (candidate.place_id, day) in variables.assigned
            ]
            if len(literals) < 2:
                continue
            count = variables.remember(
                model.NewIntVar(0, len(literals), f"tag_count:{tag}:{day}")
            )
            repeated = variables.remember(
                model.NewIntVar(0, len(literals), f"tag_repeat:{tag}:{day}")
            )
            model.Add(count == sum(literals))
            model.AddMaxEquality(repeated, [count - 1, 0])
            costs.append(repeated * coefficient)
    return sum(costs)


def build_consecutive_tag_repetition_cost(
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    maximum: int,
) -> cp_model.LinearExpr:
    place_ids = {candidate.place_id for candidate in problem.valid_places}
    tags_by_id = {
        candidate.place_id: meaningful_tags(candidate.tags)
        for candidate in problem.valid_places
    }
    costs = []
    for (origin, destination, _day), arc in variables.arc.items():
        if origin not in place_ids or destination not in place_ids:
            continue
        union = tags_by_id[origin] | tags_by_id[destination]
        if not union:
            continue
        overlap = tags_by_id[origin] & tags_by_id[destination]
        coefficient = round(len(overlap) / len(union) * maximum)
        if coefficient:
            costs.append(arc * coefficient)
    return sum(costs)
