from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from math import ceil

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    PlannerCandidate,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.policies import MEAL_POLICIES
from app.modules.itinerary_planner.ports import (
    MatrixCache,
    RoutingMatrixProvider,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import (
    CandidatePair,
    MatrixCell,
    MatrixLocation,
    RoutingErrorCode,
    RoutingPhaseError,
    RoutingProblem,
    SafeTravel,
    STRAIGHT_LINE_PROVIDER,
    STRAIGHT_LINE_WARNING,
    SparseArc,
    TravelMatrix,
)
from app.shared.tools.transport_cost import TransportCostEstimator


DEFAULT_NEIGHBOR_LIMIT = 12
ROUTING_PROFILE = "auto"
BUFFER_POLICY_VERSION = "safe-travel-v1"
PRIORITY_VALUES = {CandidatePriority.user_input, CandidatePriority.url}


def deduplicate_locations(
    problem: PreparedPlanningProblem,
    *,
    coordinate_precision: int = 6,
) -> tuple[tuple[MatrixLocation, ...], dict[str, str], dict[str, tuple[str, ...]]]:
    candidates = sorted(problem.candidate_by_id.values(), key=lambda item: item.place_id)
    by_coordinate: dict[str, list[str]] = defaultdict(list)
    coordinates: dict[str, tuple[float, float]] = {}
    for candidate in candidates:
        latitude = round(candidate.coordinates.latitude, coordinate_precision)
        longitude = round(candidate.coordinates.longitude, coordinate_precision)
        key = f"geo:{latitude:.{coordinate_precision}f},{longitude:.{coordinate_precision}f}"
        by_coordinate[key].append(candidate.place_id)
        coordinates[key] = (latitude, longitude)

    locations: list[MatrixLocation] = []
    candidate_to_node: dict[str, str] = {}
    node_to_candidates: dict[str, tuple[str, ...]] = {}
    for index, key in enumerate(sorted(by_coordinate)):
        node_id = f"matrix:{index}"
        latitude, longitude = coordinates[key]
        candidate_ids = tuple(sorted(by_coordinate[key]))
        locations.append(MatrixLocation(node_id, latitude, longitude, key))
        node_to_candidates[node_id] = candidate_ids
        candidate_to_node.update({candidate_id: node_id for candidate_id in candidate_ids})
    return tuple(locations), candidate_to_node, node_to_candidates


def matrix_cache_key(
    locations: tuple[MatrixLocation, ...],
    profile: str,
    provider_namespace: str,
) -> str:
    identity = "|".join(
        [profile, provider_namespace, BUFFER_POLICY_VERSION]
        + [location.canonical_key for location in locations]
    )
    return sha256(identity.encode("utf-8")).hexdigest()


def safe_travel(
    cell: MatrixCell,
    estimator: TransportCostEstimator,
    profile: str,
    people: int,
) -> SafeTravel:
    if not cell.reachable or cell.duration_seconds is None or cell.distance_meters is None:
        raise ValueError("Cannot create travel values from an unreachable matrix cell")
    raw_minutes = ceil(cell.duration_seconds / 60)
    safe_minutes = max(raw_minutes + 5, ceil(raw_minutes * 1.15))
    distance_meters = ceil(cell.distance_meters)
    daytime_cost, late_night_surcharge = estimator.estimate(
        distance_meters,
        profile,
        people,
    )
    return SafeTravel(
        raw_minutes=raw_minutes,
        safe_minutes=safe_minutes,
        distance_meters=distance_meters,
        transport_cost_per_person=daytime_cost,
        late_night_surcharge_per_person=late_night_surcharge,
    )


def _candidate_bounds(
    problem: PreparedPlanningProblem,
    candidate: PlannerCandidate | PlannerFoodCandidate,
    day: int,
) -> tuple[int, int] | None:
    if isinstance(candidate, PlannerFoodCandidate):
        bounds: list[tuple[int, int]] = []
        for meal in candidate.supported_meals:
            starts = problem.meal_eligibility.get((candidate.place_id, day, meal), ())
            policy = MEAL_POLICIES[meal]
            bounds.extend(
                (window.start_minute + policy.duration_minutes, window.end_minute)
                for window in starts
            )
        if not bounds:
            return None
        return min(value[0] for value in bounds), max(value[1] for value in bounds)

    windows = problem.feasible_windows.get((candidate.place_id, day), ())
    if not windows:
        return None
    return (
        min(window.start_minute + candidate.duration_minutes for window in windows),
        max(window.end_minute - candidate.duration_minutes for window in windows),
    )


def feasible_arc_days(
    problem: PreparedPlanningProblem,
    origin_id: str,
    destination_id: str,
    travel_minutes: int,
) -> frozenset[int]:
    origin = problem.candidate_by_id[origin_id]
    destination = problem.candidate_by_id[destination_id]
    common_days = problem.feasible_days[origin_id] & problem.feasible_days[destination_id]
    feasible: set[int] = set()
    for day in common_days:
        origin_bounds = _candidate_bounds(problem, origin, day)
        destination_bounds = _candidate_bounds(problem, destination, day)
        if (
            origin_bounds is not None
            and destination_bounds is not None
            and origin_bounds[0] + travel_minutes <= destination_bounds[1]
        ):
            feasible.add(day)
    return frozenset(feasible)


def _all_candidate_travel(
    problem: PreparedPlanningProblem,
    matrix: TravelMatrix,
    candidate_to_node: dict[str, str],
    estimator: TransportCostEstimator,
    profile: str,
) -> dict[CandidatePair, SafeTravel]:
    result: dict[CandidatePair, SafeTravel] = {}
    ids = sorted(problem.candidate_by_id)
    for origin_id in ids:
        for destination_id in ids:
            if origin_id == destination_id:
                continue
            origin_node = candidate_to_node[origin_id]
            destination_node = candidate_to_node[destination_id]
            if origin_node == destination_node:
                result[(origin_id, destination_id)] = SafeTravel(0, 0, 0, 0)
                continue
            cell = matrix.cell(origin_node, destination_node)
            if cell.reachable:
                result[(origin_id, destination_id)] = safe_travel(
                    cell, estimator, profile, problem.trip.people
                )
    return result


def _validate_matrix(
    matrix: TravelMatrix,
    expected_nodes: tuple[str, ...],
    profile: str,
) -> None:
    size = len(expected_nodes)
    valid_shape = len(matrix.cells) == size and all(
        len(row) == size for row in matrix.cells
    )
    if matrix.node_ids != expected_nodes or matrix.profile != profile or not valid_shape:
        raise RoutingPhaseError(
            RoutingErrorCode.matrix_invalid_response,
            "Routing matrix nodes, profile, or dimensions do not match the request.",
        )


def _weak_components(ids: set[str], pairs: set[CandidatePair]) -> list[set[str]]:
    adjacency: dict[str, set[str]] = {candidate_id: set() for candidate_id in ids}
    for origin, destination in pairs:
        adjacency[origin].add(destination)
        adjacency[destination].add(origin)
    components: list[set[str]] = []
    unseen = set(ids)
    while unseen:
        pending = [unseen.pop()]
        component: set[str] = set()
        while pending:
            node = pending.pop()
            component.add(node)
            neighbors = adjacency[node] & unseen
            unseen -= neighbors
            pending.extend(neighbors)
        components.append(component)
    return components


def build_sparse_arcs(
    problem: PreparedPlanningProblem,
    travel: dict[CandidatePair, SafeTravel],
    *,
    neighbor_limit: int = DEFAULT_NEIGHBOR_LIMIT,
) -> tuple[tuple[SparseArc, ...], tuple[str, ...]]:
    feasible: dict[CandidatePair, frozenset[int]] = {}
    for pair, values in travel.items():
        days = feasible_arc_days(problem, *pair, values.safe_minutes)
        if days:
            feasible[pair] = days

    selected: set[CandidatePair] = set()
    reasons: dict[CandidatePair, set[str]] = defaultdict(set)
    ids = set(problem.candidate_by_id)
    for origin_id in sorted(ids):
        neighbors = sorted(
            (pair for pair in feasible if pair[0] == origin_id),
            key=lambda pair: (travel[pair].safe_minutes, pair[1]),
        )
        selected.update(neighbors[:neighbor_limit])

    for origin_id, targets in problem.related_by_place.items():
        for target in targets:
            pair = (origin_id, target)
            if pair in feasible:
                selected.add(pair)
                reasons[pair].add("relationship")

    food_ids = {candidate.place_id for candidate in problem.valid_food}
    activity_ids = ids - food_ids
    for origin_ids, destination_ids in (
        (activity_ids, food_ids),
        (food_ids, activity_ids),
    ):
        for origin_id in origin_ids:
            options = [
                pair
                for pair in feasible
                if pair[0] == origin_id and pair[1] in destination_ids
            ]
            if options:
                pair = min(options, key=lambda item: (travel[item].safe_minutes, item))
                selected.add(pair)
                reasons[pair].add("meal_access")

    for candidate_id, candidate in problem.candidate_by_id.items():
        if candidate.priority not in PRIORITY_VALUES:
            continue
        incoming = [pair for pair in feasible if pair[1] == candidate_id]
        outgoing = [pair for pair in feasible if pair[0] == candidate_id]
        for options, reason in ((incoming, "priority_in"), (outgoing, "priority_out")):
            if options and not any(pair in selected for pair in options):
                pair = min(options, key=lambda item: (travel[item].safe_minutes, item))
                selected.add(pair)
                reasons[pair].add(reason)

    while len(components := _weak_components(ids, selected)) > 1:
        component_index = {
            candidate_id: index
            for index, component in enumerate(components)
            for candidate_id in component
        }
        bridges = [
            pair
            for pair in feasible
            if component_index[pair[0]] != component_index[pair[1]]
        ]
        if not bridges:
            break
        bridge = min(bridges, key=lambda pair: (travel[pair].safe_minutes, pair))
        selected.add(bridge)
        reasons[bridge].add("component_bridge")

    warnings: list[str] = []
    for candidate_id, candidate in problem.candidate_by_id.items():
        if candidate.priority in PRIORITY_VALUES and not any(
            candidate_id in pair for pair in feasible
        ):
            warnings.append(
                f"{RoutingErrorCode.unreachable_priority.value}: {candidate_id} has "
                "no reachable, time-feasible candidate pair."
            )

    arcs = [
        SparseArc(
            origin_id=pair[0],
            destination_id=pair[1],
            feasible_days=feasible[pair],
            travel=travel[pair],
            forced_reasons=frozenset(reasons[pair]),
        )
        for pair in selected
    ]
    zero = SafeTravel(0, 0, 0, 0)
    for day in range(1, problem.trip.days + 1):
        for candidate_id in sorted(ids):
            if day not in problem.feasible_days[candidate_id]:
                continue
            arcs.append(
                SparseArc(f"__start__:{day}", candidate_id, frozenset({day}), zero)
            )
            arcs.append(
                SparseArc(candidate_id, f"__end__:{day}", frozenset({day}), zero)
            )
    return tuple(sorted(arcs, key=lambda arc: (arc.origin_id, arc.destination_id))), tuple(warnings)


async def build_routing_problem(
    problem: PreparedPlanningProblem,
    provider: RoutingMatrixProvider | None,
    estimator: TransportCostEstimator | None,
    *,
    cache: MatrixCache | None = None,
    profile: str = ROUTING_PROFILE,
    neighbor_limit: int = DEFAULT_NEIGHBOR_LIMIT,
    provider_namespace: str = "valhalla:unknown",
) -> RoutingProblem:
    if provider is None:
        raise RoutingPhaseError(
            RoutingErrorCode.matrix_provider_not_configured,
            "Routing matrix provider is not configured.",
        )
    if estimator is None:
        raise RoutingPhaseError(
            RoutingErrorCode.transport_cost_not_configured,
            "Transport cost estimator is not configured.",
        )
    locations, candidate_to_node, node_to_candidates = deduplicate_locations(problem)
    cache_key = matrix_cache_key(locations, profile, provider_namespace)
    matrix = await cache.get(cache_key) if cache is not None else None
    if matrix is None:
        matrix = await provider.matrix(locations, profile)
        matrix = TravelMatrix(
            node_ids=matrix.node_ids,
            cells=matrix.cells,
            profile=matrix.profile,
            provider=matrix.provider,
            provider_version=matrix.provider_version,
            cache_key=cache_key,
        )
        if cache is not None and matrix.provider != STRAIGHT_LINE_PROVIDER:
            await cache.put(cache_key, matrix)
    expected_nodes = tuple(location.node_id for location in locations)
    _validate_matrix(matrix, expected_nodes, profile)
    travel = _all_candidate_travel(
        problem, matrix, candidate_to_node, estimator, profile
    )
    sparse_arcs, warnings = build_sparse_arcs(
        problem, travel, neighbor_limit=neighbor_limit
    )
    if matrix.provider == STRAIGHT_LINE_PROVIDER:
        warnings = (STRAIGHT_LINE_WARNING, *warnings)
    return RoutingProblem(
        locations=locations,
        candidate_to_matrix_node=candidate_to_node,
        matrix_node_to_candidates=node_to_candidates,
        matrix=matrix,
        travel_by_candidate_pair=travel,
        sparse_arcs=sparse_arcs,
        neighbor_limit=neighbor_limit,
        warnings=warnings,
    )
