from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.itinerary_planner.activity_day_domains import (
    MIN_ACTIVITY_SEPARATORS_PER_DAY,
)
from app.modules.itinerary_planner.contract import MealType

if TYPE_CHECKING:
    from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
    from app.modules.itinerary_planner.routing_models import RoutingProblem

MEALS_PER_DAY = len(MealType)


@dataclass(frozen=True, slots=True)
class ProjectedPoolViolation:
    code: str
    day: int
    message: str
    required: int | None = None
    available: int | None = None
    candidate_id: str | None = None


class ProjectedPoolPreflightError(ValueError):
    def __init__(self, violations: tuple[ProjectedPoolViolation, ...]) -> None:
        self.violations = violations
        super().__init__(
            "Projected candidate pool failed preflight: "
            + "; ".join(item.message for item in violations)
        )


def validate_projected_pool(problem: PreparedPlanningProblem) -> None:
    """Reject projected day domains that cannot support the daily model."""
    violations: list[ProjectedPoolViolation] = []
    food_ids = {item.place_id for item in problem.valid_food}

    for day in range(1, problem.trip.days + 1):
        feasible_place_ids = {
            item.place_id
            for item in problem.valid_places
            if day in problem.feasible_days[item.place_id]
        }
        if len(feasible_place_ids) < MIN_ACTIVITY_SEPARATORS_PER_DAY:
            violations.append(
                _count_violation(
                    "insufficient_activity_separators",
                    day,
                    MIN_ACTIVITY_SEPARATORS_PER_DAY,
                    len(feasible_place_ids),
                    "activity separators between meals",
                )
            )

        matched = _distinct_meal_match_count(
            problem,
            day,
            {food_id for food_id in food_ids if day in problem.feasible_days[food_id]},
        )
        if matched < MEALS_PER_DAY:
            violations.append(
                _count_violation(
                    "missing_distinct_meal_coverage",
                    day,
                    MEALS_PER_DAY,
                    matched,
                    "distinct restaurant meal matching",
                )
            )

        for candidate_id, feasible in problem.feasible_days.items():
            if day not in feasible:
                continue
            if not problem.feasible_windows.get((candidate_id, day)):
                violations.append(
                    ProjectedPoolViolation(
                        code="missing_candidate_window",
                        day=day,
                        candidate_id=candidate_id,
                        message=(
                            f"day {day}: candidate {candidate_id} has no feasible "
                            "opening window after projection"
                        ),
                    )
                )

    if violations:
        raise ProjectedPoolPreflightError(tuple(violations))


def validate_routing_connectivity(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
) -> None:
    """Require one basic route-connected component viable for each day."""
    food_ids = {item.place_id for item in problem.valid_food}
    place_ids = {item.place_id for item in problem.valid_places}
    violations: list[ProjectedPoolViolation] = []
    for day in range(1, problem.trip.days + 1):
        day_ids = {
            candidate_id
            for candidate_id, feasible in problem.feasible_days.items()
            if day in feasible
        }
        adjacency = {candidate_id: set() for candidate_id in day_ids}
        for arc in routing.sparse_arcs:
            if (
                arc.is_virtual
                or day not in arc.feasible_days
                or arc.origin_id not in day_ids
                or arc.destination_id not in day_ids
                or (arc.origin_id in food_ids and arc.destination_id in food_ids)
            ):
                continue
            adjacency[arc.origin_id].add(arc.destination_id)
            adjacency[arc.destination_id].add(arc.origin_id)

        if not any(
            len(component & place_ids) >= MIN_ACTIVITY_SEPARATORS_PER_DAY
            and _distinct_meal_match_count(
                problem,
                day,
                component & food_ids,
            )
            == MEALS_PER_DAY
            for component in _components(adjacency)
        ):
            violations.append(
                ProjectedPoolViolation(
                    code="insufficient_routing_connectivity",
                    day=day,
                    required=1,
                    available=0,
                    message=(
                        f"day {day}: no route-connected component contains at "
                        "least two activities and a distinct three-meal matching"
                    ),
                )
            )
    if violations:
        raise ProjectedPoolPreflightError(tuple(violations))


def _distinct_meal_match_count(
    problem: PreparedPlanningProblem,
    day: int,
    allowed_food_ids: set[str],
) -> int:
    choices = {
        meal: sorted(
            food_id
            for food_id in allowed_food_ids
            if (food_id, day, meal) in problem.meal_eligibility
        )
        for meal in MealType
    }
    assigned: dict[str, MealType] = {}

    def assign(meal: MealType, seen: set[str]) -> bool:
        for food_id in choices[meal]:
            if food_id in seen:
                continue
            seen.add(food_id)
            previous = assigned.get(food_id)
            if previous is None or assign(previous, seen):
                assigned[food_id] = meal
                return True
        return False

    return sum(assign(meal, set()) for meal in MealType)


def _components(adjacency: dict[str, set[str]]) -> tuple[set[str], ...]:
    unseen = set(adjacency)
    result: list[set[str]] = []
    while unseen:
        pending = [unseen.pop()]
        component: set[str] = set()
        while pending:
            candidate_id = pending.pop()
            component.add(candidate_id)
            neighbors = adjacency[candidate_id] & unseen
            unseen -= neighbors
            pending.extend(neighbors)
        result.append(component)
    return tuple(result)


def _count_violation(
    code: str,
    day: int,
    required: int,
    available: int,
    label: str,
) -> ProjectedPoolViolation:
    return ProjectedPoolViolation(
        code=code,
        day=day,
        required=required,
        available=available,
        message=f"day {day}: {label} {available}/{required}",
    )
