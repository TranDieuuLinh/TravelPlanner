from __future__ import annotations

from math import ceil

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.constraints import (
    fit_transition_window,
    is_drink_dessert,
    is_entertainment,
    is_restaurant,
    is_restaurant_to_restaurant,
    is_travelplace,
    long_transition_allowed,
)
from app.modules.itinerary_planner.beam_search.deadline import BeamSearchDeadline
from app.modules.itinerary_planner.beam_search.models import DaySearchState
from app.modules.itinerary_planner.beam_search.pruning import prune_day_states
from app.modules.itinerary_planner.beam_search.scoring import candidate_score
from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    MealType,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.optimizer.result import ScheduledStop
from app.modules.itinerary_planner.policies import (
    MEAL_POLICIES,
    MINIMUM_MEAL_START_GAPS,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem


MEAL_ORDER = (MealType.breakfast, MealType.lunch, MealType.dinner)
PRIORITY_VALUES = frozenset({CandidatePriority.user_input, CandidatePriority.url})


def candidate_ids_by_day(
    problem: PreparedPlanningProblem,
) -> dict[int, tuple[str, ...]]:
    ordered = tuple(sorted(problem.candidate_by_id))
    return {
        day: tuple(
            candidate_id
            for candidate_id in ordered
            if day in problem.feasible_days.get(candidate_id, ())
        )
        for day in range(1, problem.trip.days + 1)
    }


def search_day(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    day: int,
    candidate_ids: tuple[str, ...],
    matrix_node_position: dict[str, int],
    used_ids: frozenset[str],
    quality: dict[str, float],
    adjusted_ratings: dict[str, float | None],
    distance_q3: float | None,
    review_q3: float | None,
    config: BeamSearchConfig,
    deadline: BeamSearchDeadline,
) -> tuple[DaySearchState, ...]:
    frontier = (DaySearchState(),)
    terminals: list[DaySearchState] = []
    fallbacks: tuple[DaySearchState, ...] = ()
    while frontier and not deadline.expired(force=True):
        next_frontier: list[DaySearchState] = []
        for state in frontier:
            if has_all_meals(state) and state.stops:
                terminals.append(state)
            if len(state.stops) >= config.max_stops_per_day:
                continue
            next_frontier.extend(
                expand_state(
                    problem,
                    routing,
                    state,
                    day=day,
                    candidate_ids=candidate_ids,
                    matrix_node_position=matrix_node_position,
                    used_ids=used_ids,
                    quality=quality,
                    adjusted_ratings=adjusted_ratings,
                    distance_q3=distance_q3,
                    review_q3=review_q3,
                    config=config,
                    deadline=deadline,
                )
            )
            if deadline.expired(force=True):
                break
        if next_frontier:
            fallbacks = prune_day_states(
                (*fallbacks, *next_frontier), config.beam_width, problem
            )
        if not next_frontier or deadline.expired(force=True):
            break
        frontier = prune_day_states(next_frontier, config.beam_width, problem)
    complete_states = prune_day_states(terminals, config.beam_width, problem)
    if complete_states:
        return complete_states
    return prune_day_states(fallbacks, config.beam_width, problem)


def expand_state(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    state: DaySearchState,
    *,
    day: int,
    candidate_ids: tuple[str, ...],
    matrix_node_position: dict[str, int],
    used_ids: frozenset[str],
    quality: dict[str, float],
    adjusted_ratings: dict[str, float | None],
    distance_q3: float | None,
    review_q3: float | None,
    config: BeamSearchConfig,
    deadline: BeamSearchDeadline,
) -> list[DaySearchState]:
    output: list[DaySearchState] = []
    unavailable = used_ids | state.selected_ids
    for candidate_id in candidate_ids:
        if deadline.expired():
            break
        candidate = problem.candidate_by_id[candidate_id]
        if candidate_id in unavailable and is_travelplace(candidate):
            continue
        travel = None
        if state.last_id is not None:
            travel = routing.travel_by_candidate_pair.get((state.last_id, candidate_id))
            if travel is None:
                continue
            previous = problem.candidate_by_id[state.last_id]
            origin_node = routing.candidate_to_matrix_node[state.last_id]
            destination_node = routing.candidate_to_matrix_node[candidate_id]
            matrix_cell = routing.matrix.cells[matrix_node_position[origin_node]][
                matrix_node_position[destination_node]
            ]
            if matrix_cell.food_to_food and is_restaurant_to_restaurant(
                previous, candidate
            ):
                continue
            if not long_transition_allowed(
                distance_meters=travel.distance_meters,
                distance_q3=distance_q3,
                adjusted_rating=adjusted_ratings.get(candidate_id),
                review_count=candidate.review_count,
                review_q3=review_q3,
                config=config,
            ):
                continue
        meal_choices = _meal_choices(candidate, state)
        if (
            is_restaurant(candidate)
            and state.restaurant_count < config.target_restaurant_count
        ):
            meal_choices = (*meal_choices, None)
        for meal_type in meal_choices:
            if (
                is_drink_dessert(candidate)
                and state.drink_dessert_count >= config.max_drink_desserts_per_day
            ):
                continue
            arrival = state.end_minute + (travel.safe_minutes if travel else 0)
            windows, duration, meal_start_floor = _candidate_windows(
                problem, candidate_id, candidate, day, meal_type, config
            )
            if meal_start_floor is not None:
                arrival = max(arrival, meal_start_floor)
                previous_meal = _previous_meal_start(state, meal_type)
                if previous_meal is not None:
                    arrival = max(
                        arrival,
                        previous_meal
                        + MINIMUM_MEAL_START_GAPS[
                            (MealType.breakfast, MealType.lunch)
                            if meal_type == MealType.lunch
                            else (MealType.lunch, MealType.dinner)
                        ],
                    )
            fit = fit_transition_window(
                arrival, duration, windows, config.max_wait_minutes
            )
            if fit is None:
                continue
            start, end = fit
            candidate_cost = ceil(candidate.price.cost)
            travel_cost = 0
            if travel is not None:
                travel_cost = travel.transport_cost_per_person
                if state.end_minute >= 1320:
                    travel_cost += travel.late_night_surcharge_per_person
            next_cost = state.cost + candidate_cost + travel_cost
            budget = problem.trip.budget
            if (
                budget.amount is not None
                and budget.source != "estimated_daily_cost"
                and next_cost > budget.amount
            ):
                continue
            stop = ScheduledStop(candidate_id, day, start, end, meal_type)
            output.append(
                DaySearchState(
                    stops=(*state.stops, stop),
                    selected_ids=state.selected_ids | {candidate_id},
                    priority_ids=(
                        state.priority_ids | {candidate_id}
                        if candidate.priority in PRIORITY_VALUES
                        else state.priority_ids
                    ),
                    last_id=candidate_id,
                    end_minute=end,
                    meal_starts=(
                        (*state.meal_starts, (meal_type, start))
                        if meal_type is not None
                        else state.meal_starts
                    ),
                    score=state.score
                    + candidate_score(
                        problem, candidate, state, start, travel, quality, config
                    ),
                    cost=next_cost,
                    restaurant_count=state.restaurant_count
                    + int(is_restaurant(candidate)),
                    travelplace_count=state.travelplace_count
                    + int(is_travelplace(candidate)),
                    drink_dessert_count=state.drink_dessert_count
                    + int(is_drink_dessert(candidate)),
                    entertainment_count=state.entertainment_count
                    + int(is_entertainment(candidate)),
                )
            )
    return output


def has_all_meals(state: DaySearchState) -> bool:
    return _meal_set(state) == frozenset(MEAL_ORDER)


def _candidate_windows(problem, candidate_id, candidate, day, meal_type, config):
    if isinstance(candidate, PlannerFoodCandidate):
        if meal_type is None:
            windows = _restaurant_fill_windows(
                problem.feasible_windows.get((candidate_id, day), ()),
                config.restaurant_fill_windows,
            )
            return windows, candidate.duration_minutes, None
        policy = MEAL_POLICIES[meal_type]
        return (
            problem.meal_eligibility.get((candidate_id, day, meal_type), ()),
            policy.duration_minutes,
            policy.earliest_start,
        )
    return (
        problem.feasible_windows.get((candidate_id, day), ()),
        candidate.duration_minutes,
        None,
    )


def _restaurant_fill_windows(windows, fill_windows):
    return tuple(
        (max(window.start_minute, start), min(window.end_minute, end))
        for window in windows
        for start, end in fill_windows
        if max(window.start_minute, start) < min(window.end_minute, end)
    )


def _meal_choices(candidate, state):
    if not isinstance(candidate, PlannerFoodCandidate):
        return (None,)
    next_meal = next(
        (meal for meal in MEAL_ORDER if meal not in _meal_set(state)), None
    )
    return (next_meal,) if next_meal in candidate.supported_meals else ()


def _meal_set(state: DaySearchState) -> frozenset[MealType]:
    return frozenset(meal for meal, _ in state.meal_starts)


def _previous_meal_start(state: DaySearchState, meal_type: MealType) -> int | None:
    index = MEAL_ORDER.index(meal_type)
    if index == 0:
        return None
    return dict(state.meal_starts).get(MEAL_ORDER[index - 1])
