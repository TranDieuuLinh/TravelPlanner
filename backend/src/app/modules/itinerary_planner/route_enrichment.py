from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from math import ceil

from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.ports import RouteDetailProvider
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import (
    RouteDetail,
    RouteLegRequest,
    RoutingPhaseError,
    RoutingProblem,
    SafeTravel,
    STRAIGHT_LINE_PROVIDER,
    STRAIGHT_LINE_WARNING,
)
from app.shared.tools.transport_cost import TransportCostEstimator


@dataclass(frozen=True, slots=True)
class EnrichedRouteLeg:
    origin_id: str
    destination_id: str
    day: int
    duration_minutes: int
    distance_meters: int
    encoded_polyline: str | None
    provider: str
    geometry_available: bool
    accommodation_transfer_direction: str | None = None


@dataclass(frozen=True, slots=True)
class RouteEnrichmentResult:
    legs: tuple[EnrichedRouteLeg, ...]
    repair_days: frozenset[int]
    actual_minutes_by_pair: dict[tuple[str, str], int]
    actual_distance_by_pair: dict[tuple[str, str], int]
    warnings: tuple[str, ...]


async def enrich_selected_routes(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    optimization: OptimizationResult,
    provider: RouteDetailProvider | None,
    *,
    concurrency: int = 6,
    repair_tolerance_minutes: int = 2,
    days: frozenset[int] | None = None,
) -> RouteEnrichmentResult:
    del problem  # Candidate metadata is already represented by routing mappings.
    location_by_node = {location.node_id: location for location in routing.locations}
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def fetch(origin_id: str, destination_id: str) -> RouteDetail | None:
        if provider is None:
            return None
        origin_node = routing.candidate_to_matrix_node[origin_id]
        destination_node = routing.candidate_to_matrix_node[destination_id]
        if origin_node == destination_node:
            return RouteDetail(origin_node, destination_node, 0, 0, None, "same_location")
        request = RouteLegRequest(
            location_by_node[origin_node],
            location_by_node[destination_node],
        )
        try:
            async with semaphore:
                details = await provider.route((request,), routing.matrix.profile)
            return details[0] if details else None
        except (RoutingPhaseError, IndexError):
            return None

    selected_arcs = tuple(
        arc for arc in optimization.selected_arcs if days is None or arc.day in days
    )
    selected_transfers = tuple(
        transfer
        for transfer in optimization.accommodation_transfers
        if days is None or transfer.day in days
    )
    route_legs = [
        (arc.origin_id, arc.destination_id, arc.day, None)
        for arc in selected_arcs
    ]
    route_legs.extend(
        (
            transfer.accommodation_id
            if transfer.direction == "start"
            else transfer.candidate_id,
            transfer.candidate_id
            if transfer.direction == "start"
            else transfer.accommodation_id,
            transfer.day,
            transfer.direction,
        )
        for transfer in selected_transfers
    )
    details = await asyncio.gather(
        *(fetch(origin_id, destination_id) for origin_id, destination_id, _, _ in route_legs)
    )
    stop_by_key = {(stop.place_id, stop.day): stop for stop in optimization.scheduled_stops}
    legs: list[EnrichedRouteLeg] = []
    repair_days: set[int] = set()
    actual_minutes: dict[tuple[str, str], int] = {}
    actual_distances: dict[tuple[str, str], int] = {}
    warnings: list[str] = []
    for route_leg, detail in zip(route_legs, details, strict=True):
        origin_id, destination_id, day, transfer_direction = route_leg
        pair = (origin_id, destination_id)
        matrix_travel = routing.travel_by_candidate_pair[pair]
        if detail is None:
            warnings.append(
                f"Route geometry unavailable for {origin_id} -> {destination_id}; "
                "matrix safe duration was retained."
            )
            duration = matrix_travel.safe_minutes
            distance = matrix_travel.distance_meters
            provider_name = routing.matrix.provider
            polyline = None
        else:
            duration = ceil(detail.duration_seconds / 60)
            distance = ceil(detail.distance_meters)
            provider_name = detail.provider
            polyline = detail.encoded_polyline
            actual_minutes[pair] = duration
            actual_distances[pair] = distance
            if transfer_direction is None:
                destination = stop_by_key[(destination_id, day)]
                origin = stop_by_key[(origin_id, day)]
                exceeds_safe = (
                    duration
                    > matrix_travel.safe_minutes + repair_tolerance_minutes
                )
                breaks_timeline = destination.start_minute < origin.end_minute + duration
                if exceeds_safe and breaks_timeline:
                    repair_days.add(day)
            elif duration > matrix_travel.safe_minutes:
                repair_days.add(day)
            if detail.provider == STRAIGHT_LINE_PROVIDER:
                warnings.append(STRAIGHT_LINE_WARNING)
        legs.append(
            EnrichedRouteLeg(
                origin_id,
                destination_id,
                day,
                duration,
                distance,
                polyline,
                provider_name,
                polyline is not None,
                transfer_direction,
            )
        )
    return RouteEnrichmentResult(
        tuple(legs),
        frozenset(repair_days),
        actual_minutes,
        actual_distances,
        tuple(warnings),
    )


def apply_route_corrections(
    routing: RoutingProblem,
    enrichment: RouteEnrichmentResult,
    estimator: TransportCostEstimator,
    people: int,
) -> RoutingProblem:
    corrected = dict(routing.travel_by_candidate_pair)
    for pair, actual_minutes in enrichment.actual_minutes_by_pair.items():
        if pair not in corrected or actual_minutes <= corrected[pair].safe_minutes:
            continue
        distance = enrichment.actual_distance_by_pair[pair]
        daytime, night = estimator.estimate(distance, routing.matrix.profile, people)
        corrected[pair] = SafeTravel(
            raw_minutes=actual_minutes,
            safe_minutes=actual_minutes,
            distance_meters=distance,
            transport_cost_per_person=daytime,
            late_night_surcharge_per_person=night,
        )
    sparse = tuple(
        replace(arc, travel=corrected[(arc.origin_id, arc.destination_id)])
        if (arc.origin_id, arc.destination_id) in corrected
        else arc
        for arc in routing.sparse_arcs
    )
    return replace(
        routing,
        travel_by_candidate_pair=corrected,
        sparse_arcs=sparse,
    )


def invalid_timeline_days(
    optimization: OptimizationResult,
    enrichment: RouteEnrichmentResult,
) -> frozenset[int]:
    stops = {(stop.place_id, stop.day): stop for stop in optimization.scheduled_stops}
    invalid = set()
    for leg in enrichment.legs:
        if leg.accommodation_transfer_direction is not None:
            continue
        origin = stops[(leg.origin_id, leg.day)]
        destination = stops[(leg.destination_id, leg.day)]
        if destination.start_minute < origin.end_minute + leg.duration_minutes:
            invalid.add(leg.day)
    return frozenset(invalid)
