import asyncio

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.optimizer import (
    ObjectiveWeights,
    SolverConfig,
    optimize_itinerary,
)
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.route_enrichment import (
    apply_route_corrections,
    enrich_selected_routes,
    invalid_timeline_days,
    route_correction_pairs,
)
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.tests.factories import candidate, payload
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    continuity_candidates,
    meal_candidates,
)
from app.modules.itinerary_planner.tests.routing_fakes import (
    GeneratedMatrixProvider,
    GeneratedRouteDetailProvider,
)
from app.modules.itinerary_planner.timeline_reflow import try_reflow_timeline


def test_route_reflow_shifts_timeline_and_reuses_route_details() -> None:
    raw = payload(
        days=1,
        places=[candidate("required", priority="user_input"), *continuity_candidates()],
        foods=meal_candidates(1),
    )
    for index, item in enumerate([*raw["places"], *raw["food"]]):
        item["coordinates"] = {
            "latitude": 21.02 + index / 1000,
            "longitude": 105.84,
        }
    problem = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))
    estimator = XanhSmTransportCostEstimator()
    routing = asyncio.run(
        build_routing_problem(problem, GeneratedMatrixProvider(), estimator)
    )
    baseline = optimize_itinerary(
        problem,
        routing,
        config=SolverConfig(
            priority_timeout_seconds=2,
            utility_timeout_seconds=4,
            utility_parallel_workers=1,
            max_utility_no_improvement_rounds=0,
        ),
    )
    stops = {(stop.place_id, stop.day): stop for stop in baseline.scheduled_stops}
    chosen = min(
        baseline.selected_arcs,
        key=lambda arc: stops[(arc.destination_id, arc.day)].start_minute
        - stops[(arc.origin_id, arc.day)].end_minute
        - routing.travel_by_candidate_pair[
            (arc.origin_id, arc.destination_id)
        ].safe_minutes,
    )
    pair = (chosen.origin_id, chosen.destination_id)
    slack = (
        stops[(chosen.destination_id, chosen.day)].start_minute
        - stops[(chosen.origin_id, chosen.day)].end_minute
        - routing.travel_by_candidate_pair[pair].safe_minutes
    )
    node_pair = (
        routing.candidate_to_matrix_node[chosen.origin_id],
        routing.candidate_to_matrix_node[chosen.destination_id],
    )
    provider = GeneratedRouteDetailProvider(
        duration_by_pair={
            node_pair: (routing.travel_by_candidate_pair[pair].safe_minutes + slack + 3)
            * 60
        }
    )
    cache = {}
    details = asyncio.run(
        enrich_selected_routes(
            problem, routing, baseline, provider, detail_cache=cache
        )
    )

    assert route_correction_pairs(routing, details)
    corrected = apply_route_corrections(routing, details, estimator, problem.trip.people)
    reflowed = try_reflow_timeline(
        problem,
        corrected,
        baseline,
        details.repair_days,
        ObjectiveWeights(),
    )

    assert reflowed is not None
    assert reflowed.selected_ids == baseline.selected_ids
    assert reflowed.selected_arcs == baseline.selected_arcs
    call_count = len(provider.calls)
    repaired_details = asyncio.run(
        enrich_selected_routes(
            problem,
            corrected,
            reflowed,
            provider,
            days=details.repair_days,
            detail_cache=cache,
        )
    )
    assert len(provider.calls) == call_count
    assert not repaired_details.repair_days
    assert not invalid_timeline_days(reflowed, repaired_details)
