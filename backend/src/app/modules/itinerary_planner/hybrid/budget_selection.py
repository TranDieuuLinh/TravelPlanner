from __future__ import annotations

from app.modules.itinerary_planner.accommodation_selection import (
    BUDGET_AWARE_SOURCES,
    select_accommodation_anchor_id,
)
from app.modules.itinerary_planner.contract import (
    FoodVenueType,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem

FOOD_OPTIONS_PER_MEAL = 6


def is_budget_aware(problem: PreparedPlanningProblem) -> bool:
    return (
        problem.trip.budget.amount is not None
        and problem.trip.budget.source in BUDGET_AWARE_SOURCES
    )


def expand_budget_reserve(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    available: set[str],
) -> None:
    if not is_budget_aware(problem):
        return
    available.update(
        candidate_id
        for candidate_id, feasible_days in problem.feasible_days.items()
        if day in feasible_days and candidate_id not in used_ids
    )


def select_food_options(
    ranked: list[PlannerFoodCandidate],
) -> tuple[str, ...]:
    selected = list(ranked[:FOOD_OPTIONS_PER_MEAL])
    if selected and all(
        item.venue_type == FoodVenueType.drink_dessert for item in selected
    ):
        restaurant = next(
            (
                item
                for item in ranked[FOOD_OPTIONS_PER_MEAL:]
                if item.venue_type == FoodVenueType.restaurant
            ),
            None,
        )
        if restaurant is not None:
            selected[-1] = restaurant
    return tuple(item.place_id for item in selected)


def food_corridor_cost(
    candidate: PlannerFoodCandidate,
    corridor: tuple[str | None, str | None],
    routing: RoutingProblem,
) -> int:
    before, after = corridor
    pairs = [
        pair
        for pair in ((before, candidate.place_id), (candidate.place_id, after))
        if pair[0] is not None and pair[1] is not None
    ]
    travel_cost = sum(
        routing.travel_by_candidate_pair[pair].transport_cost_per_person
        for pair in pairs
        if pair in routing.travel_by_candidate_pair
    )
    return round(candidate.price.cost) + travel_cost


def budget_access_penalty(
    problem: PreparedPlanningProblem,
    candidate_id: str,
    routing: RoutingProblem,
    weight: int,
) -> int:
    if weight <= 0 or problem.trip.budget.amount is None:
        return 0
    accommodation_id = select_accommodation_anchor_id(problem)
    if accommodation_id is None:
        return 0
    costs = []
    for pair in (
        (accommodation_id, candidate_id),
        (candidate_id, accommodation_id),
    ):
        travel = routing.travel_by_candidate_pair.get(pair)
        if travel is not None:
            costs.append(travel.transport_cost_per_person)
    return sum(costs) // 10_000 * weight
