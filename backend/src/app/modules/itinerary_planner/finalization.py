from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from math import ceil

from app.modules.itinerary_planner.contract import CandidatePriority
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.output_contract import (
    ItineraryDay,
    ItineraryPlannerOutput,
    ItineraryRouteLeg,
    ItineraryStop,
    SolverMetadata,
    SolverPassMetadata,
    SourceMixAudit,
    SourceMixCounts,
    UnscheduledPriority,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.route_enrichment import RouteEnrichmentResult
from app.modules.itinerary_planner.routing_models import RoutingProblem

PRIORITY_VALUES = {CandidatePriority.user_input, CandidatePriority.url}
LATE_NIGHT_START_MINUTE = 22 * 60


def finalize_itinerary(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    optimization: OptimizationResult,
    enrichment: RouteEnrichmentResult,
    warnings: list[str],
    phase_timings_ms: dict[str, int],
) -> ItineraryPlannerOutput:
    food_ids = {food.place_id for food in problem.valid_food}
    stops_by_day: dict[int, list[ItineraryStop]] = defaultdict(list)
    for stop in optimization.scheduled_stops:
        candidate = problem.candidate_by_id[stop.place_id]
        stops_by_day[stop.day].append(
            ItineraryStop(
                place_id=stop.place_id,
                name=candidate.name,
                kind="food" if stop.place_id in food_ids else "place",
                priority=candidate.priority,
                start_minute=stop.start_minute,
                end_minute=stop.end_minute,
                duration_minutes=stop.end_minute - stop.start_minute,
                meal_type=stop.meal_type,
                coordinates=candidate.coordinates,
                address=candidate.address,
                notes=candidate.notes,
                tags=candidate.tags,
                cost_per_person=ceil(candidate.price.cost),
            )
        )

    legs_by_day: dict[int, list[ItineraryRouteLeg]] = defaultdict(list)
    raw_legs_by_day = defaultdict(list)
    for leg in enrichment.legs:
        raw_legs_by_day[leg.day].append(leg)
        legs_by_day[leg.day].append(
            ItineraryRouteLeg(
                from_place_id=leg.origin_id,
                to_place_id=leg.destination_id,
                duration_minutes=leg.duration_minutes,
                distance_meters=leg.distance_meters,
                encoded_polyline=leg.encoded_polyline,
                provider=leg.provider,
                geometry_available=leg.geometry_available,
            )
        )

    days = []
    for day in range(1, problem.trip.days + 1):
        day_stops = sorted(stops_by_day[day], key=lambda item: (item.start_minute, item.place_id))
        activity_minutes = sum(stop.duration_minutes for stop in day_stops)
        travel_minutes = sum(leg.duration_minutes for leg in raw_legs_by_day[day])
        candidate_cost = sum(stop.cost_per_person for stop in day_stops)
        transport_cost = sum(
            _transport_cost(routing, leg.origin_id, leg.destination_id, day_stops)
            for leg in raw_legs_by_day[day]
        )
        days.append(
            ItineraryDay(
                day=day,
                date=problem.trip.start_date + timedelta(days=day - 1),
                stops=day_stops,
                legs=legs_by_day[day],
                activity_minutes=activity_minutes,
                travel_minutes=travel_minutes,
                cost_per_person=candidate_cost + transport_cost,
            )
        )

    selected = set(optimization.selected_ids)
    unscheduled = [
        UnscheduledPriority(
            place_id=item.place_id,
            name=item.name,
            priority=item.priority,
            reason_code=item.reason_code,
            message=item.message,
        )
        for item in problem.unscheduled_priority
    ]
    unscheduled.extend(
        UnscheduledPriority(
            place_id=candidate.place_id,
            name=candidate.name,
            priority=candidate.priority,
            reason_code="not_selected_by_optimizer",
            message="No feasible placement preserved this candidate in the optimized itinerary.",
        )
        for candidate in problem.candidate_by_id.values()
        if candidate.priority in PRIORITY_VALUES and candidate.place_id not in selected
    )
    optional_ids = {
        candidate.place_id
        for candidate in problem.candidate_by_id.values()
        if candidate.priority not in PRIORITY_VALUES
    }
    solver_time = sum(item.wall_time_ms for item in optimization.passes)
    return ItineraryPlannerOutput(
        destination=problem.trip.destination,
        timezone=problem.trip.timezone,
        days=days,
        total_cost_per_person=optimization.total_cost_per_person,
        budget_per_person=problem.trip.budget.amount,
        currency=problem.trip.budget.currency,
        solver=SolverMetadata(
            status=optimization.status,
            optimality_proven=optimization.optimality_proven,
            objective_value=optimization.objective_value,
            objective_policy_version=optimization.objective_policy_version,
            objective_components=optimization.objective_components,
            passes=[
                SolverPassMetadata(
                    name=item.name,
                    status=item.status,
                    objective_value=item.objective_value,
                    wall_time_ms=item.wall_time_ms,
                    optimality_proven=item.optimality_proven,
                )
                for item in optimization.passes
            ],
            planning_time_ms=solver_time,
        ),
        source_mix=[
            SourceMixAudit(
                period=item.period,
                target=SourceMixCounts(
                    special=item.target_special,
                    offer=item.target_offer,
                ),
                actual=SourceMixCounts(
                    special=item.actual_special,
                    offer=item.actual_offer,
                ),
                quota_fallback=item.fallback_used,
                fallback_reason=(
                    "source_mix_quota_fallback" if item.fallback_used else None
                ),
            )
            for item in optimization.source_mix
        ],
        unscheduled=unscheduled,
        discarded_optional_count=(
            len(problem.discarded_optional) + len(optional_ids - selected)
        ),
        warnings=list(dict.fromkeys(warnings)),
        phase_timings_ms=phase_timings_ms,
    )


def _transport_cost(routing, origin_id, destination_id, stops):
    travel = routing.travel_by_candidate_pair[(origin_id, destination_id)]
    origin = next(stop for stop in stops if stop.place_id == origin_id)
    night = (
        travel.late_night_surcharge_per_person
        if origin.end_minute >= LATE_NIGHT_START_MINUTE
        else 0
    )
    return travel.transport_cost_per_person + night
