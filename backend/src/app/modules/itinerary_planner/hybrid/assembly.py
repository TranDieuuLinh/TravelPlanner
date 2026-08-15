from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from math import ceil

from app.modules.itinerary_planner.optimizer.result import (
    OptimizationResult,
    ScheduledStop,
    SelectedAccommodationTransfer,
    SourceMixPeriodResult,
)
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.policies import (
    MINIMUM_OVERNIGHT_REST_MINUTES,
    OVERNIGHT_END_MINUTE,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem

LATE_NIGHT_START_MINUTE = 22 * 60
StopsByDay = dict[int, list[ScheduledStop]]


def assemble_hybrid_result(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    day_results: Sequence[OptimizationResult],
) -> OptimizationResult:
    accommodation_id, transfers, accommodation_total = _select_accommodation(
        problem, routing, day_results
    )
    total_cost = sum(item.total_cost_per_person for item in day_results)
    total_cost += accommodation_total
    budget = problem.trip.budget
    if (
        budget.amount is not None
        and budget.source != "estimated_daily_cost"
        and total_cost > budget.amount
    ):
        raise OptimizationError("INFEASIBLE", "hybrid_budget")

    components: dict[str, int] = defaultdict(int)
    for result in day_results:
        for name, value in result.objective_components.items():
            components[name] += value
    selected_ids = tuple(
        sorted({item for result in day_results for item in result.selected_ids})
    )
    return OptimizationResult(
        status="FEASIBLE",
        optimality_proven=False,
        selected_ids=selected_ids,
        scheduled_stops=tuple(
            stop for result in day_results for stop in result.scheduled_stops
        ),
        selected_arcs=tuple(
            arc for result in day_results for arc in result.selected_arcs
        ),
        selected_accommodation_id=accommodation_id,
        accommodation_transfers=transfers,
        total_cost_per_person=total_cost,
        user_input_count=sum(
            problem.candidate_by_id[item].priority.value == "user_input"
            for item in selected_ids
        ),
        url_count=sum(
            problem.candidate_by_id[item].priority.value == "url"
            for item in selected_ids
        ),
        objective_value=sum(result.objective_value for result in day_results),
        objective_components=dict(components),
        objective_policy_version="hybrid-activity-corridor-v2",
        passes=tuple(item for result in day_results for item in result.passes),
        source_mix=_combine_source_mix(day_results),
    )


def _select_accommodation(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    results: Sequence[OptimizationResult],
) -> tuple[str | None, tuple[SelectedAccommodationTransfer, ...], int]:
    stops_by_day: StopsByDay = {
        day: sorted(
            (
                stop
                for result in results
                for stop in result.scheduled_stops
                if stop.day == day
            ),
            key=lambda stop: (stop.start_minute, stop.place_id),
        )
        for day in range(1, problem.trip.days + 1)
    }
    if any(not stops for stops in stops_by_day.values()):
        raise OptimizationError("INFEASIBLE", "hybrid_empty_day")
    if not problem.accommodations or not problem.accommodation_nights:
        _validate_plain_overnight_rest(stops_by_day)
        return None, (), 0
    options: list[tuple[int, str, tuple[SelectedAccommodationTransfer, ...]]] = []
    for accommodation in problem.accommodations:
        transfers: list[SelectedAccommodationTransfer] = []
        transfer_cost = 0
        valid = True
        for day, stops in stops_by_day.items():
            departure_minutes = 0
            if day > 1:
                pair = (accommodation.place_id, stops[0].place_id)
                if pair not in routing.travel_by_candidate_pair:
                    valid = False
                    break
                departure = routing.travel_by_candidate_pair[pair]
                departure_minutes = departure.safe_minutes
                transfer_cost += departure.transport_cost_per_person
                transfers.append(
                    SelectedAccommodationTransfer(
                        accommodation.place_id, stops[0].place_id, day, "start"
                    )
                )
            if day < problem.trip.days:
                pair = (stops[-1].place_id, accommodation.place_id)
                if pair not in routing.travel_by_candidate_pair:
                    valid = False
                    break
                travel = routing.travel_by_candidate_pair[pair]
                if stops[-1].end_minute + travel.safe_minutes > OVERNIGHT_END_MINUTE:
                    valid = False
                    break
                transfer_cost += travel.transport_cost_per_person
                if stops[-1].end_minute >= LATE_NIGHT_START_MINUTE:
                    transfer_cost += travel.late_night_surcharge_per_person
                transfers.append(
                    SelectedAccommodationTransfer(
                        accommodation.place_id, stops[-1].place_id, day, "end"
                    )
                )
            if day > 1:
                previous = stops_by_day[day - 1][-1]
                previous_pair = (previous.place_id, accommodation.place_id)
                previous_travel = routing.travel_by_candidate_pair.get(previous_pair)
                if previous_travel is None or (
                    stops[0].start_minute
                    - departure_minutes
                    + 1440
                    - previous.end_minute
                    - previous_travel.safe_minutes
                    < MINIMUM_OVERNIGHT_REST_MINUTES
                ):
                    valid = False
                    break
        if valid:
            stay = problem.accommodation_cost_per_person_by_id[accommodation.place_id]
            stay *= problem.accommodation_nights
            options.append(
                (stay + transfer_cost, accommodation.place_id, tuple(transfers))
            )
    if not options:
        raise OptimizationError("INFEASIBLE", "hybrid_accommodation")
    total, accommodation_id, transfers = min(options)
    return accommodation_id, transfers, ceil(total)


def _validate_plain_overnight_rest(stops_by_day: StopsByDay) -> None:
    for day in range(1, len(stops_by_day)):
        if (
            stops_by_day[day + 1][0].start_minute
            + 1440
            - stops_by_day[day][-1].end_minute
            < MINIMUM_OVERNIGHT_REST_MINUTES
        ):
            raise OptimizationError("INFEASIBLE", "hybrid_overnight_rest")


def _combine_source_mix(
    results: Sequence[OptimizationResult],
) -> tuple[SourceMixPeriodResult, ...]:
    output: list[SourceMixPeriodResult] = []
    for period, target_tenths in (("morning", 7), ("evening", 6)):
        special = sum(
            item.actual_special
            for result in results
            for item in result.source_mix
            if item.period == period
        )
        offer = sum(
            item.actual_offer
            for result in results
            for item in result.source_mix
            if item.period == period
        )
        total = special + offer
        target_special = (total * target_tenths + 5) // 10
        output.append(
            SourceMixPeriodResult(
                period,
                target_special,
                total - target_special,
                special,
                offer,
            )
        )
    return tuple(output)
