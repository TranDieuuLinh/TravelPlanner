from __future__ import annotations

from dataclasses import replace
from math import ceil, floor

from app.modules.itinerary_planner.optimizer.config import ObjectiveWeights
from app.modules.itinerary_planner.optimizer.result import (
    OptimizationResult,
    ScheduledStop,
)
from app.modules.itinerary_planner.policies import (
    IDEAL_INTER_STOP_WAIT_MINUTES,
    ITINERARY_START_MINUTE,
    LIGHT_INTER_STOP_WAIT_MINUTES,
    MAX_INTER_STOP_WAIT_MINUTES,
    MEAL_POLICIES,
    MINIMUM_MEAL_START_GAPS,
    MINIMUM_OVERNIGHT_REST_MINUTES,
    OVERNIGHT_END_MINUTE,
    STANDARD_DAY_END_MINUTE,
    STRONG_INTER_STOP_WAIT_MINUTES,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem


def try_reflow_timeline(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    baseline: OptimizationResult,
    affected_days: frozenset[int],
    weights: ObjectiveWeights,
    *,
    max_inter_stop_wait_minutes: int | None = MAX_INTER_STOP_WAIT_MINUTES,
) -> OptimizationResult | None:
    """Push existing stops later without changing selection or route order."""
    stop_by_key = {(stop.place_id, stop.day): stop for stop in baseline.scheduled_stops}
    updated = dict(stop_by_key)
    arcs_by_day = _arcs_by_day(baseline)
    transfers = {
        (transfer.day, transfer.direction): transfer
        for transfer in baseline.accommodation_transfers
    }

    for day in sorted(affected_days):
        ordered = _ordered_day_stops(baseline, day, arcs_by_day.get(day, ()))
        if not ordered:
            return None
        previous: ScheduledStop | None = None
        shifted_meal_starts = {}
        start_transfer = transfers.get((day, "start"))
        for stop in ordered:
            minimum_start = stop.start_minute
            if previous is None and start_transfer is not None:
                pair = (start_transfer.accommodation_id, stop.place_id)
                minimum_start = max(
                    minimum_start,
                    ITINERARY_START_MINUTE
                    + routing.travel_by_candidate_pair[pair].safe_minutes,
                )
            elif previous is not None:
                pair = (previous.place_id, stop.place_id)
                travel = routing.travel_by_candidate_pair[pair].safe_minutes
                minimum_start = max(minimum_start, previous.end_minute + travel)
            if stop.meal_type is not None:
                minimum_start = max(
                    [
                        minimum_start,
                        *(
                            shifted_meal_starts[earlier] + gap
                            for (earlier, later), gap in MINIMUM_MEAL_START_GAPS.items()
                            if later == stop.meal_type
                            and earlier in shifted_meal_starts
                        ),
                    ]
                )
            shifted = _fit_stop(problem, stop, minimum_start)
            if shifted is None:
                return None
            if previous is not None and max_inter_stop_wait_minutes is not None:
                travel = routing.travel_by_candidate_pair[
                    (previous.place_id, shifted.place_id)
                ].safe_minutes
                waiting = shifted.start_minute - previous.end_minute - travel
                if waiting > max_inter_stop_wait_minutes:
                    return None
            updated[(shifted.place_id, day)] = shifted
            if shifted.meal_type is not None:
                shifted_meal_starts[shifted.meal_type] = shifted.start_minute
            previous = shifted

        end_transfer = transfers.get((day, "end"))
        if end_transfer is not None and previous is not None:
            pair = (previous.place_id, end_transfer.accommodation_id)
            if (
                previous.end_minute
                + routing.travel_by_candidate_pair[pair].safe_minutes
                > OVERNIGHT_END_MINUTE
            ):
                return None

    stops = tuple(
        sorted(
            updated.values(),
            key=lambda stop: (stop.day, stop.start_minute, stop.place_id),
        )
    )
    if not _meal_gaps_are_valid(stops) or not _overnight_rest_is_valid(
        problem, routing, baseline, stops
    ):
        return None
    total_cost = _total_cost(problem, routing, baseline, stops)
    budget = problem.trip.budget
    if (
        budget.amount is not None
        and budget.source != "estimated_daily_cost"
        and total_cost > floor(budget.amount)
    ):
        return None
    components, objective_value = _updated_objective(
        problem, routing, baseline, stops, total_cost, weights
    )
    return replace(
        baseline,
        scheduled_stops=stops,
        total_cost_per_person=total_cost,
        objective_components=components,
        objective_value=objective_value,
    )


def _fit_stop(
    problem: PreparedPlanningProblem,
    stop: ScheduledStop,
    minimum_start: int,
) -> ScheduledStop | None:
    duration = stop.end_minute - stop.start_minute
    if stop.meal_type is not None:
        windows = problem.meal_eligibility.get(
            (stop.place_id, stop.day, stop.meal_type), ()
        )
        for window in windows:
            start = max(minimum_start, window.start_minute)
            if start <= window.end_minute:
                return replace(stop, start_minute=start, end_minute=start + duration)
        return None
    for window in problem.feasible_windows.get((stop.place_id, stop.day), ()):
        start = max(minimum_start, window.start_minute)
        if start + duration <= window.end_minute:
            return replace(stop, start_minute=start, end_minute=start + duration)
    return None


def _arcs_by_day(
    baseline: OptimizationResult,
) -> dict[int, tuple[tuple[str, str], ...]]:
    grouped: dict[int, list[tuple[str, str]]] = {}
    for arc in baseline.selected_arcs:
        grouped.setdefault(arc.day, []).append((arc.origin_id, arc.destination_id))
    return {day: tuple(arcs) for day, arcs in grouped.items()}


def _ordered_day_stops(
    baseline: OptimizationResult,
    day: int,
    arcs: tuple[tuple[str, str], ...],
) -> tuple[ScheduledStop, ...]:
    day_stops = {
        stop.place_id: stop for stop in baseline.scheduled_stops if stop.day == day
    }
    if len(day_stops) <= 1:
        return tuple(day_stops.values())
    outgoing = dict(arcs)
    destinations = {destination for _, destination in arcs}
    starts = [place_id for place_id in day_stops if place_id not in destinations]
    if len(starts) != 1:
        return ()
    ordered = []
    visited = set()
    current = starts[0]
    while current in day_stops and current not in visited:
        visited.add(current)
        ordered.append(day_stops[current])
        current = outgoing.get(current, "")
    return tuple(ordered) if len(ordered) == len(day_stops) else ()


def _meal_gaps_are_valid(stops: tuple[ScheduledStop, ...]) -> bool:
    starts = {
        (stop.day, stop.meal_type): stop.start_minute
        for stop in stops
        if stop.meal_type is not None
    }
    return all(
        starts[(day, later)] >= starts[(day, earlier)] + gap
        for day in {stop.day for stop in stops}
        for (earlier, later), gap in MINIMUM_MEAL_START_GAPS.items()
    )


def _overnight_rest_is_valid(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    baseline: OptimizationResult,
    stops: tuple[ScheduledStop, ...],
) -> bool:
    by_day = {
        day: tuple(
            sorted(
                (stop for stop in stops if stop.day == day),
                key=lambda item: item.start_minute,
            )
        )
        for day in range(1, problem.trip.days + 1)
    }
    transfers = {
        (transfer.day, transfer.direction): transfer
        for transfer in baseline.accommodation_transfers
    }
    for day in range(1, problem.trip.days):
        current_last = by_day[day][-1]
        next_first = by_day[day + 1][0]
        return_minutes = departure_minutes = 0
        end_transfer = transfers.get((day, "end"))
        start_transfer = transfers.get((day + 1, "start"))
        if end_transfer is not None:
            return_minutes = routing.travel_by_candidate_pair[
                (current_last.place_id, end_transfer.accommodation_id)
            ].safe_minutes
        if start_transfer is not None:
            departure_minutes = routing.travel_by_candidate_pair[
                (start_transfer.accommodation_id, next_first.place_id)
            ].safe_minutes
        if (
            next_first.start_minute
            - departure_minutes
            + 1440
            - current_last.end_minute
            - return_minutes
            < MINIMUM_OVERNIGHT_REST_MINUTES
        ):
            return False
    return True


def _total_cost(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    baseline: OptimizationResult,
    stops: tuple[ScheduledStop, ...],
) -> int:
    total = sum(
        ceil(problem.candidate_by_id[item].price.cost) for item in baseline.selected_ids
    )
    if baseline.selected_accommodation_id is not None:
        total += (
            problem.accommodation_cost_per_person_by_id[
                baseline.selected_accommodation_id
            ]
            * problem.accommodation_nights
        )
    stop_by_key = {(stop.place_id, stop.day): stop for stop in stops}
    for arc in baseline.selected_arcs:
        travel = routing.travel_by_candidate_pair[(arc.origin_id, arc.destination_id)]
        total += travel.transport_cost_per_person
        if stop_by_key[(arc.origin_id, arc.day)].end_minute >= 22 * 60:
            total += travel.late_night_surcharge_per_person
    for transfer in baseline.accommodation_transfers:
        pair = (
            (transfer.accommodation_id, transfer.candidate_id)
            if transfer.direction == "start"
            else (transfer.candidate_id, transfer.accommodation_id)
        )
        travel = routing.travel_by_candidate_pair[pair]
        total += travel.transport_cost_per_person
        if (
            transfer.direction == "end"
            and stop_by_key[(transfer.candidate_id, transfer.day)].end_minute >= 22 * 60
        ):
            total += travel.late_night_surcharge_per_person
    return total


def _updated_objective(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    baseline: OptimizationResult,
    stops: tuple[ScheduledStop, ...],
    total_cost: int,
    weights: ObjectiveWeights,
) -> tuple[dict[str, int], int]:
    components = dict(baseline.objective_components)
    previous = {name: components.get(name, 0) for name in _REFLOW_COSTS}
    stop_by_key = {(stop.place_id, stop.day): stop for stop in stops}
    travel_minutes = sum(
        routing.travel_by_candidate_pair[
            (arc.origin_id, arc.destination_id)
        ].safe_minutes
        for arc in baseline.selected_arcs
    ) + sum(
        routing.travel_by_candidate_pair[
            (item.accommodation_id, item.candidate_id)
            if item.direction == "start"
            else (item.candidate_id, item.accommodation_id)
        ].safe_minutes
        for item in baseline.accommodation_transfers
    )
    waits = []
    for arc in baseline.selected_arcs:
        origin = stop_by_key[(arc.origin_id, arc.day)]
        destination = stop_by_key[(arc.destination_id, arc.day)]
        safe = routing.travel_by_candidate_pair[
            (arc.origin_id, arc.destination_id)
        ].safe_minutes
        waits.append(destination.start_minute - origin.end_minute - safe)
    components["travelTimeCost"] = travel_minutes * weights.travel_minute
    components["idleWaitingCost"] = sum(
        _waiting_cost(value, weights) for value in waits
    )
    components["mealDeviationCost"] = sum(
        abs(stop.start_minute - MEAL_POLICIES[stop.meal_type].target_start)
        * weights.meal_deviation_minute
        for stop in stops
        if stop.meal_type is not None
    )
    old_late = sum(
        max(0, stop.end_minute - STANDARD_DAY_END_MINUTE)
        for stop in baseline.scheduled_stops
    )
    new_late = sum(max(0, stop.end_minute - STANDARD_DAY_END_MINUTE) for stop in stops)
    components["fatigueCost"] = (
        previous["fatigueCost"] + (new_late - old_late) * weights.late_minute
    )
    budget = problem.trip.budget
    components["budgetOverageCost"] = (
        max(0, total_cost - floor(budget.amount or 0))
        // 10_000
        * weights.budget_overage_10k
        if budget.amount is not None and budget.source == "estimated_daily_cost"
        else 0
    )
    delta = sum(components[name] - previous[name] for name in _REFLOW_COSTS)
    return components, baseline.objective_value - delta


def _waiting_cost(minutes: int, weights: ObjectiveWeights) -> int:
    return (
        max(0, minutes - IDEAL_INTER_STOP_WAIT_MINUTES) * weights.waiting_minute
        + max(0, minutes - LIGHT_INTER_STOP_WAIT_MINUTES) * weights.waiting_minute * 2
        + max(0, minutes - STRONG_INTER_STOP_WAIT_MINUTES) * weights.waiting_minute * 6
    )


_REFLOW_COSTS = (
    "travelTimeCost",
    "idleWaitingCost",
    "mealDeviationCost",
    "fatigueCost",
    "budgetOverageCost",
)
