from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from math import ceil

from app.modules.itinerary_planner.contract import CandidatePriority
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.output_contract import (
    DailyCostBreakdown,
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
from app.modules.itinerary_planner.policies import (
    ACCOMMODATION_RELOCATION_DISTANCE_METERS,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.quality import bayesian_adjusted_rating_by_id
from app.modules.itinerary_planner.route_enrichment import RouteEnrichmentResult
from app.modules.itinerary_planner.routing_models import RoutingProblem
from app.shared.tools.daily_cost import DailyCostCalculator

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
    if (
        problem.trip.budget.source == "estimated_daily_cost"
        and problem.trip.budget.amount is not None
        and optimization.total_cost_per_person > problem.trip.budget.amount
    ):
        warnings.append(
            "Actual itinerary cost exceeds the approximate budget estimate; "
            "the estimate is a soft planning target."
        )
    food_ids = {food.place_id for food in problem.valid_food}
    entertainment_ids = {item.place_id for item in problem.valid_entertainment}
    bayesian_ratings = bayesian_adjusted_rating_by_id(
        problem.candidate_by_id.values()
    )
    accommodation_bayesian_ratings = bayesian_adjusted_rating_by_id(
        problem.accommodations
    )
    selected_accommodation = (
        problem.accommodation_by_id.get(optimization.selected_accommodation_id)
        if optimization.selected_accommodation_id
        else None
    )
    if selected_accommodation is not None:
        selected_accommodation = selected_accommodation.model_copy(
            update={
                "bayesian_rating": accommodation_bayesian_ratings.get(
                    selected_accommodation.place_id
                )
            }
        )
    accommodation_cost = (
        problem.accommodation_cost_per_person_by_id.get(
            optimization.selected_accommodation_id, 0
        )
        if optimization.selected_accommodation_id
        else 0
    )
    stops_by_day: dict[int, list[ItineraryStop]] = defaultdict(list)
    for stop in optimization.scheduled_stops:
        candidate = problem.candidate_by_id[stop.place_id]
        canonical_place_id = problem.canonical_place_id_by_candidate_id.get(
            stop.place_id, stop.place_id
        )
        repeated_meal = stop.place_id in problem.canonical_place_id_by_candidate_id
        item_suffix = f":{stop.meal_type.value}" if repeated_meal else ""
        stops_by_day[stop.day].append(
            ItineraryStop(
                item_id=f"planner:{stop.day}:{canonical_place_id}{item_suffix}",
                place_id=canonical_place_id,
                name=candidate.name,
                kind=(
                    "food"
                    if stop.place_id in food_ids
                    else "entertainment"
                    if stop.place_id in entertainment_ids
                    else "place"
                ),
                priority=candidate.priority,
                start_minute=stop.start_minute,
                end_minute=stop.end_minute,
                duration_minutes=stop.end_minute - stop.start_minute,
                meal_type=stop.meal_type,
                coordinates=candidate.coordinates,
                address=candidate.address,
                notes=candidate.notes,
                personal_notes=candidate.personal_notes,
                tags=candidate.tags,
                image_urls=candidate.image_urls,
                rating=candidate.rating,
                bayesian_rating=bayesian_ratings.get(candidate.place_id),
                review_count=candidate.review_count,
                opening_hours=candidate.opening_hours,
                cost_per_person=ceil(candidate.price.cost),
            )
        )

    legs_by_day: dict[int, list[ItineraryRouteLeg]] = defaultdict(list)
    raw_legs_by_day = defaultdict(list)
    for leg in enrichment.legs:
        if leg.accommodation_transfer_direction is not None:
            continue
        raw_legs_by_day[leg.day].append(leg)
        legs_by_day[leg.day].append(
            ItineraryRouteLeg(
                from_place_id=problem.canonical_place_id_by_candidate_id.get(
                    leg.origin_id, leg.origin_id
                ),
                to_place_id=problem.canonical_place_id_by_candidate_id.get(
                    leg.destination_id, leg.destination_id
                ),
                duration_minutes=leg.duration_minutes,
                distance_meters=leg.distance_meters,
                encoded_polyline=leg.encoded_polyline,
                provider=leg.provider,
                geometry_available=leg.geometry_available,
                cost_per_person=_transport_cost(
                    routing,
                    leg.origin_id,
                    leg.destination_id,
                    optimization.scheduled_stops,
                ),
            )
        )
    accommodation_transport_by_day: dict[int, int] = defaultdict(int)
    accommodation_minutes_by_day: dict[int, int] = defaultdict(int)
    enriched_accommodation_legs = {
        (leg.origin_id, leg.destination_id, leg.day): leg
        for leg in enrichment.legs
        if leg.accommodation_transfer_direction is not None
    }
    for transfer in optimization.accommodation_transfers:
        pair = (
            (transfer.accommodation_id, transfer.candidate_id)
            if transfer.direction == "start"
            else (transfer.candidate_id, transfer.accommodation_id)
        )
        travel = routing.travel_by_candidate_pair[pair]
        accommodation_leg_cost = travel.transport_cost_per_person
        if transfer.direction == "end":
            origin = next(
                stop
                for stop in optimization.scheduled_stops
                if stop.place_id == transfer.candidate_id and stop.day == transfer.day
            )
            if origin.end_minute >= LATE_NIGHT_START_MINUTE:
                accommodation_leg_cost += travel.late_night_surcharge_per_person
        accommodation_transport_by_day[transfer.day] += accommodation_leg_cost
        enriched_leg = enriched_accommodation_legs.get((*pair, transfer.day))
        duration_minutes = (
            enriched_leg.duration_minutes if enriched_leg else travel.safe_minutes
        )
        distance_meters = (
            enriched_leg.distance_meters if enriched_leg else travel.distance_meters
        )
        accommodation_minutes_by_day[transfer.day] += duration_minutes
        accommodation_leg = ItineraryRouteLeg(
            from_place_id=problem.canonical_place_id_by_candidate_id.get(
                pair[0], pair[0]
            ),
            to_place_id=problem.canonical_place_id_by_candidate_id.get(
                pair[1], pair[1]
            ),
            duration_minutes=duration_minutes,
            distance_meters=distance_meters,
            encoded_polyline=(enriched_leg.encoded_polyline if enriched_leg else None),
            provider=(
                enriched_leg.provider if enriched_leg else routing.matrix.provider
            ),
            geometry_available=bool(enriched_leg and enriched_leg.geometry_available),
            cost_per_person=accommodation_leg_cost,
        )
        if not accommodation_leg.geometry_available:
            warnings.append(
                "Route geometry unavailable for accommodation transfer "
                f"{pair[0]} -> {pair[1]} on day {transfer.day}."
            )
        if transfer.direction == "start":
            legs_by_day[transfer.day].insert(0, accommodation_leg)
        else:
            legs_by_day[transfer.day].append(accommodation_leg)
        if travel.distance_meters > ACCOMMODATION_RELOCATION_DISTANCE_METERS:
            warnings.append(
                "Selected accommodation requires a transfer over 50 km on "
                f"day {transfer.day}; no closer candidate produced a better "
                "feasible itinerary."
            )

    days = []
    for day in range(1, problem.trip.days + 1):
        day_stops = sorted(
            stops_by_day[day], key=lambda item: (item.start_minute, item.place_id)
        )
        activity_minutes = sum(stop.duration_minutes for stop in day_stops)
        travel_minutes = (
            sum(leg.duration_minutes for leg in raw_legs_by_day[day])
            + accommodation_minutes_by_day[day]
        )
        food_cost = sum(
            stop.cost_per_person for stop in day_stops if stop.kind == "food"
        )
        activity_cost = sum(
            stop.cost_per_person
            for stop in day_stops
            if stop.kind in {"place", "entertainment"}
        )
        transport_cost = (
            sum(
                _transport_cost(
                    routing,
                    leg.origin_id,
                    leg.destination_id,
                    optimization.scheduled_stops,
                )
                for leg in raw_legs_by_day[day]
            )
            + accommodation_transport_by_day[day]
        )
        daily_cost = DailyCostCalculator.estimate(
            accommodation=(
                accommodation_cost if day <= problem.accommodation_nights else 0
            ),
            food=food_cost,
            local_transport=transport_cost,
            activities=activity_cost,
            currency=problem.trip.budget.currency,
        )
        days.append(
            ItineraryDay(
                day=day,
                date=problem.trip.start_date + timedelta(days=day - 1),
                stops=day_stops,
                legs=legs_by_day[day],
                activity_minutes=activity_minutes,
                travel_minutes=travel_minutes,
                cost_per_person=daily_cost.total,
                cost_breakdown=DailyCostBreakdown(
                    accommodation=daily_cost.accommodation,
                    food=daily_cost.food,
                    local_transport=daily_cost.local_transport,
                    activities=daily_cost.activities,
                    misc=daily_cost.misc,
                    total=daily_cost.total,
                    currency=daily_cost.currency,
                ),
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
            notes=item.notes,
            personal_notes=item.personal_notes,
            source_refs=list(item.source_refs),
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
            notes=candidate.notes,
            personal_notes=candidate.personal_notes,
            source_refs=(
                [candidate.notes.source_url]
                if candidate.notes and candidate.notes.source_url
                else []
            ),
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
        people=problem.trip.people,
        accommodation=selected_accommodation,
        accommodation_nights=problem.accommodation_nights
        if selected_accommodation
        else 0,
        days=days,
        total_cost_per_person=optimization.total_cost_per_person,
        budget_per_person=problem.trip.budget.amount,
        budget_source=problem.trip.budget.source,
        daily_budget_estimate=problem.trip.budget.daily_estimate,
        budget_profile_version=problem.trip.budget.profile_version,
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
                    attempt_count=item.attempt_count,
                    round_count=item.round_count,
                    no_improvement_rounds=item.no_improvement_rounds,
                )
                for item in optimization.passes
            ],
            planning_time_ms=solver_time,
        ),
        evaluation=optimization.evaluation,
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
