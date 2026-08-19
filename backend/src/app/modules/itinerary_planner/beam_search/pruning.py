from __future__ import annotations

from app.modules.itinerary_planner.beam_search.constraints import (
    is_drink_dessert,
    is_entertainment,
    is_restaurant,
    is_travelplace,
)
from app.modules.itinerary_planner.contract import CandidatePriority


PRIORITY_VALUES = frozenset(
    {CandidatePriority.user_input, CandidatePriority.url}
)


def prune_day_states(states, width, problem):
    ordered = sorted(states, key=lambda state: day_sort_key(state, problem), reverse=True)
    return _diverse_top(
        ordered,
        width,
        lambda state: _state_signature(problem, state.stops, state.priority_ids),
    )


def prune_plans(states, width, problem):
    ordered = sorted(states, key=lambda state: plan_sort_key(state, problem), reverse=True)
    return _diverse_top(
        ordered,
        width,
        lambda state: _state_signature(
            problem,
            tuple(stop for day in state.days for stop in day),
            state.priority_ids,
        ),
    )


def _diverse_top(states, width, signature):
    selected = []
    seen = set()
    for state in states:
        key = signature(state)
        if key in seen:
            continue
        selected.append(state)
        seen.add(key)
        if len(selected) == width:
            return tuple(selected)
    selected_ids = {id(state) for state in selected}
    selected.extend(state for state in states if id(state) not in selected_ids)
    return tuple(selected[:width])


def _travel_signature(problem, stops):
    return tuple(sorted(
        stop.place_id
        for stop in stops
        if is_travelplace(problem.candidate_by_id[stop.place_id])
    ))


def _state_signature(problem, stops, priority_ids):
    return (
        _travel_signature(problem, stops),
        tuple(sorted(_priority_ids(problem, stops, priority_ids))),
    )


def _priority_ids(problem, stops, explicit_ids):
    return frozenset(explicit_ids) | frozenset(
        stop.place_id
        for stop in stops
        if problem.candidate_by_id[stop.place_id].priority in PRIORITY_VALUES
    )


def _priority_sort_key(problem, stops, explicit_ids):
    priority_ids = _priority_ids(problem, stops, explicit_ids)
    return (
        sum(
            problem.candidate_by_id[place_id].priority
            == CandidatePriority.user_input
            for place_id in priority_ids
        ),
        sum(
            problem.candidate_by_id[place_id].priority == CandidatePriority.url
            for place_id in priority_ids
        ),
    )


def day_sort_key(state, problem):
    # Preserve meal feasibility before applying the restaurant/category
    # preference; optional restaurant branches must not crowd out a branch
    # that still needs lunch or dinner.
    return (
        _priority_sort_key(problem, state.stops, state.priority_ids)
        + (len({meal for meal, _ in state.meal_starts}),)
        + repetition_sort_key(problem, state.stops)
        + category_sort_key(
            count_stops(problem, state.stops, is_restaurant),
            count_stops(problem, state.stops, is_travelplace),
            count_stops(problem, state.stops, is_drink_dessert),
            count_stops(problem, state.stops, is_entertainment),
            diversity_count(problem, state.stops),
            state.score,
            state.cost,
        )
        + (tuple(stop.place_id for stop in state.stops),)
    )


def plan_sort_key(state, problem):
    stops = tuple(stop for day in state.days for stop in day)
    return (
        _priority_sort_key(problem, stops, state.priority_ids)
        + distinct_coverage_sort_key(problem, stops)
        + repetition_sort_key(problem, stops)
        + category_sort_key(
            state.restaurant_count,
            state.travelplace_count,
            state.drink_dessert_count,
            state.entertainment_count,
            state.diversity_count,
            state.score,
            state.cost,
        )
        + (tuple(stop.place_id for stop in stops),)
    )


def distinct_coverage_sort_key(problem, stops):
    """Prefer new places first, then new leisure and food identities."""
    return tuple(
        len({
            stop.place_id
            for stop in stops
            if predicate(problem.candidate_by_id[stop.place_id])
        })
        for predicate in (
            is_travelplace,
            is_entertainment,
            is_drink_dessert,
            is_restaurant,
        )
    )


def repetition_sort_key(problem, stops):
    """Prefer fewer repeated visits, prioritizing leisure before restaurants."""
    return tuple(
        -_repeat_count(problem, stops, predicate)
        for predicate in (is_entertainment, is_drink_dessert, is_restaurant)
    )


def _repeat_count(problem, stops, predicate):
    ids = [stop.place_id for stop in stops if predicate(problem.candidate_by_id[stop.place_id])]
    return len(ids) - len(set(ids))


def category_sort_key(
    restaurant_count,
    travelplace_count,
    drink_dessert_count,
    entertainment_count,
    diversity_count,
    score,
    cost,
):
    return (
        restaurant_count >= 3,
        travelplace_count,
        restaurant_count >= 2,
        entertainment_count > 0,
        drink_dessert_count,
        entertainment_count,
        restaurant_count >= 1,
        diversity_count,
        score,
        -cost,
    )


def count_stops(problem, stops, predicate):
    return sum(predicate(problem.candidate_by_id[stop.place_id]) for stop in stops)


def diversity_count(problem, stops):
    categories = set()
    for stop in stops:
        candidate = problem.candidate_by_id[stop.place_id]
        if is_restaurant(candidate):
            categories.add("restaurant")
        elif is_drink_dessert(candidate):
            categories.add("drink_dessert")
        elif is_entertainment(candidate):
            categories.add("entertainment")
        elif is_travelplace(candidate):
            categories.add("travelplace")
    return len(categories)
