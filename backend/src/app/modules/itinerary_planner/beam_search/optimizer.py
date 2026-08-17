from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
from time import monotonic

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.constraints import (
    fit_transition_window,
    is_drink_dessert,
    is_entertainment,
    is_restaurant,
    is_restaurant_to_restaurant,
    is_travelplace,
    long_transition_allowed,
    upper_quartile,
)
from app.modules.itinerary_planner.beam_search.evaluation import evaluate_plan
from app.modules.itinerary_planner.beam_search.pruning import (
    category_sort_key,
    count_stops,
    diversity_count,
    plan_sort_key,
    prune_day_states,
    prune_plans,
)
from app.modules.itinerary_planner.beam_search.result_builder import build_day_result
from app.modules.itinerary_planner.beam_search.scoring import candidate_score
from app.modules.itinerary_planner.contract import MealType, PlannerFoodCandidate
from app.modules.itinerary_planner.hybrid.assembly import assemble_hybrid_result
from app.modules.itinerary_planner.optimizer.result import (
    OptimizationResult,
    ScheduledStop,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem
from app.modules.itinerary_planner.quality import bayesian_quality_by_id
from app.modules.itinerary_planner.policies import MEAL_POLICIES, MINIMUM_MEAL_START_GAPS


MEAL_ORDER = (MealType.breakfast, MealType.lunch, MealType.dinner)


@dataclass(frozen=True, slots=True)
class _DayState:
    stops: tuple[ScheduledStop, ...] = ()
    selected_ids: frozenset[str] = frozenset()
    last_id: str | None = None
    end_minute: int = 480
    meal_starts: tuple[tuple[MealType, int], ...] = ()
    score: float = 0.0
    cost: int = 0


@dataclass(frozen=True, slots=True)
class _PlanState:
    days: tuple[tuple[ScheduledStop, ...], ...] = ()
    selected_ids: frozenset[str] = frozenset()
    score: float = 0.0
    cost: int = 0
    restaurant_count: int = 0
    travelplace_count: int = 0
    drink_dessert_count: int = 0
    entertainment_count: int = 0
    diversity_count: int = 0


def optimize_beam_search(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    config: BeamSearchConfig | None = None,
) -> OptimizationResult:
    selected_config = config or BeamSearchConfig()
    started = monotonic()
    distance_q3 = upper_quartile(
        travel.distance_meters
        for (origin, destination), travel in routing.travel_by_candidate_pair.items()
        if origin in problem.candidate_by_id
        and destination in problem.candidate_by_id
        and travel.distance_meters > 0
    )
    review_q3 = upper_quartile(
        (
            candidate.review_count
            for candidate in problem.candidate_by_id.values()
            if candidate.review_count is not None
        ),
        quantile=selected_config.review_quantile,
    )
    quality = bayesian_quality_by_id(problem.candidate_by_id.values())
    day_search_limit = selected_config.time_limit_seconds
    if problem.trip.days > 1 and day_search_limit is not None:
        # Backtracking invokes the day search once per partial plan.  Bound
        # each invocation so alternatives do not multiply the single-day
        # timeout by the size of the global frontier.
        day_search_limit = min(day_search_limit, 0.5)
    day_search_config = replace(
        selected_config,
        beam_width=(
            max(selected_config.beam_width, selected_config.combination_beam_width)
            if problem.trip.days > 1
            else selected_config.beam_width
        ),
        time_limit_seconds=day_search_limit,
    )
    frontier = [_PlanState()]
    fallback_frontier: list[_PlanState] = []
    for day in range(1, problem.trip.days + 1):
        next_frontier: list[_PlanState] = []
        for plan in frontier:
            used_travelplaces = _travelplace_ids(
                problem, tuple(stop for day_stops in plan.days for stop in day_stops)
            )
            day_states = _search_day(
                problem,
                routing,
                day=day,
                used_ids=frozenset(used_travelplaces),
                quality=quality,
                distance_q3=distance_q3,
                review_q3=review_q3,
                config=day_search_config,
            )
            next_frontier.extend(
                _extend_plan(problem, plan, state, selected_config)
                for state in day_states
            )
        if next_frontier:
            fallback_frontier = prune_plans(
                next_frontier, selected_config.combination_beam_width, problem
            )
        frontier = prune_plans(
            next_frontier, selected_config.combination_beam_width, problem
        )
        if not frontier:
            break

    if not frontier:
        frontier = fallback_frontier
    if not frontier:
        raise ValueError("Beam Search found no candidate itinerary.")

    best = max(frontier, key=lambda state: plan_sort_key(state, problem))
    day_results = tuple(
        build_day_result(problem, routing, stops, selected_config, started)
        for stops in best.days
    )
    result = assemble_hybrid_result(problem, routing, day_results)
    complete = len(best.days) == problem.trip.days and all(
        _has_all_meals(
            _DayState(
                stops=stops,
                meal_starts=tuple(
                    (stop.meal_type, stop.start_minute)
                    for stop in stops
                    if stop.meal_type is not None
                ),
            )
        )
        for stops in best.days
    )
    result = replace(
        result,
        status="FEASIBLE" if complete else "PARTIAL",
        objective_value=round(best.score),
        objective_components={
            "beam_score": round(best.score),
            "restaurant_coverage": sum(
                is_restaurant(problem.candidate_by_id[item]) for item in best.selected_ids
            ),
        },
        objective_policy_version=selected_config.policy_version,
        optimality_proven=False,
        evaluation=evaluate_plan(problem, routing, result),
    )
    return result


def _extend_plan(problem, plan: _PlanState, state: _DayState, config) -> _PlanState:
    return _PlanState(
        days=(*plan.days, state.stops),
        selected_ids=plan.selected_ids | state.selected_ids,
        score=(
            plan.score
            + state.score
            + config.weights.travelplace_final_weight * count_stops(
                problem, state.stops, is_travelplace
            )
        ),
        cost=plan.cost + state.cost,
        restaurant_count=plan.restaurant_count
        + count_stops(problem, state.stops, is_restaurant),
        travelplace_count=plan.travelplace_count
        + count_stops(problem, state.stops, is_travelplace),
        drink_dessert_count=plan.drink_dessert_count
        + count_stops(problem, state.stops, is_drink_dessert),
        entertainment_count=plan.entertainment_count
        + count_stops(problem, state.stops, is_entertainment),
        diversity_count=plan.diversity_count
        + diversity_count(problem, state.stops),
    )


def _travelplace_ids(problem, stops):
    return {
        stop.place_id
        for stop in stops
        if is_travelplace(problem.candidate_by_id[stop.place_id])
    }


def _search_day(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    quality: dict[str, float],
    distance_q3: float | None,
    review_q3: float | None,
    config: BeamSearchConfig,
) -> tuple[_DayState, ...]:
    started = monotonic()
    frontier = (_DayState(),)
    terminals: list[_DayState] = []
    fallbacks: tuple[_DayState, ...] = ()
    while frontier:
        next_frontier: list[_DayState] = []
        for state in frontier:
            if _has_all_meals(state) and state.stops:
                terminals.append(state)
            if len(state.stops) >= config.max_stops_per_day:
                continue
            expansions = _expand_state(
                problem,
                routing,
                state,
                day=day,
                used_ids=used_ids,
                quality=quality,
                distance_q3=distance_q3,
                review_q3=review_q3,
                config=config,
            )
            next_frontier.extend(expansions)
        if next_frontier:
            fallbacks = prune_day_states(
                (*fallbacks, *next_frontier), config.beam_width, problem
            )
        if not next_frontier or (
            config.time_limit_seconds is not None
            and monotonic() - started >= config.time_limit_seconds
        ):
            break
        frontier = prune_day_states(next_frontier, config.beam_width, problem)
    complete_states = prune_day_states(terminals, config.beam_width, problem)
    if complete_states:
        return complete_states
    return prune_day_states(fallbacks, config.beam_width, problem)


def _expand_state(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    state: _DayState,
    *,
    day: int,
    used_ids: frozenset[str],
    quality: dict[str, float],
    distance_q3: float | None,
    review_q3: float | None,
    config: BeamSearchConfig,
) -> list[_DayState]:
    output: list[_DayState] = []
    unavailable = used_ids | state.selected_ids
    for candidate_id in sorted(problem.candidate_by_id):
        if day not in problem.feasible_days.get(candidate_id, ()):
            continue
        candidate = problem.candidate_by_id[candidate_id]
        # Travel places are one-time itinerary anchors.  Food and leisure
        # candidates may be revisited across days when that is the best way to
        # complete the meal/time constraints.
        if candidate_id in unavailable and is_travelplace(candidate):
            continue
        travel = None
        if state.last_id is not None:
            travel = routing.travel_by_candidate_pair.get((state.last_id, candidate_id))
            # Candidates may share one physical location (for example a meal
            # candidate and an activity at the same venue).  The routing
            # matrix legitimately reports zero distance for that pair.
            if travel is None:
                continue
            previous = problem.candidate_by_id[state.last_id]
            origin_node = routing.candidate_to_matrix_node[state.last_id]
            destination_node = routing.candidate_to_matrix_node[candidate_id]
            matrix_cell = routing.matrix.cell(origin_node, destination_node)
            if matrix_cell.food_to_food and is_restaurant_to_restaurant(
                previous, candidate
            ):
                continue
            if not long_transition_allowed(
                distance_meters=travel.distance_meters,
                distance_q3=distance_q3,
                rating=candidate.rating,
                review_count=candidate.review_count,
                review_q3=review_q3,
                config=config,
            ):
                continue
        meal_choices = _meal_choices(candidate, state)
        if (
            is_restaurant(candidate)
            and count_stops(problem, state.stops, is_restaurant)
            < config.target_restaurant_count
        ):
            # A restaurant that is not used as the next required meal may fill
            # the lunch/dinner restaurant windows as an optional stop.
            meal_choices = (*meal_choices, None)
        for meal_type in meal_choices:
            if is_drink_dessert(candidate) and _drink_dessert_count(problem, state) >= config.max_drink_desserts_per_day:
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
                _DayState(
                    stops=(*state.stops, stop),
                    selected_ids=state.selected_ids | {candidate_id},
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
                )
            )
    return output


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
    return problem.feasible_windows.get((candidate_id, day), ()), candidate.duration_minutes, None


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
    next_meal = next((meal for meal in MEAL_ORDER if meal not in _meal_set(state)), None)
    return (next_meal,) if next_meal in candidate.supported_meals else ()


def _meal_set(state: _DayState) -> frozenset[MealType]:
    return frozenset(meal for meal, _ in state.meal_starts)


def _previous_meal_start(state: _DayState, meal_type: MealType) -> int | None:
    index = MEAL_ORDER.index(meal_type)
    if index == 0:
        return None
    previous = MEAL_ORDER[index - 1]
    return dict(state.meal_starts).get(previous)


def _has_all_meals(state: _DayState) -> bool:
    return _meal_set(state) == frozenset(MEAL_ORDER)


def _drink_dessert_count(problem, state):
    return sum(
        is_drink_dessert(problem.candidate_by_id[stop.place_id]) for stop in state.stops
    )
