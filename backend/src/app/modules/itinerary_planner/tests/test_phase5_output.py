import asyncio

import pytest

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.graph import build_itinerary_planner_graph
from app.modules.itinerary_planner.nodes import _merge_enrichment
from app.modules.itinerary_planner.optimizer import SolverConfig, optimize_itinerary
from app.modules.itinerary_planner.optimizer.locks import RepairLocks
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.route_enrichment import (
    RouteEnrichmentResult,
    apply_route_corrections,
    enrich_selected_routes,
    invalid_timeline_days,
)
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    continuity_candidates,
    meal_candidates,
)
from app.modules.itinerary_planner.tests.routing_fakes import (
    GeneratedMatrixProvider,
    GeneratedRouteDetailProvider,
)

FAST_CONFIG = SolverConfig(
    priority_timeout_seconds=2,
    utility_timeout_seconds=4,
)


def test_merge_enrichment_preserves_follow_up_repair_days() -> None:
    original = RouteEnrichmentResult((), frozenset({1}), {}, {}, ("initial",))
    repaired = RouteEnrichmentResult((), frozenset({2}), {}, {}, ("follow-up",))

    merged = _merge_enrichment(original, repaired)

    assert merged.repair_days == {2}
    assert merged.warnings == ("initial", "follow-up")


def test_phase5_enriches_only_selected_arcs_and_finalizes_output() -> None:
    places = [
        candidate(
            "lake",
            priority="user_input",
            image_urls=["https://example.test/lake.jpg"],
            opening_hours={"1": [{"startMinute": 480, "endMinute": 1020}]},
        ),
        *continuity_candidates(),
    ]
    foods = [
        food("breakfast", supported_meals=["breakfast"]),
        food("lunch", supported_meals=["lunch"]),
        food("dinner", supported_meals=["dinner"]),
    ]
    for index, item in enumerate([*places, *foods]):
        item["coordinates"] = {
            "latitude": 21.02 + index / 1000,
            "longitude": 105.84,
        }
    places[0]["notes"] = {
        "text": "Đến trước 8 giờ",
        "sourceType": "url",
        "sourceUrl": "https://example.test/video",
    }
    provider = GeneratedRouteDetailProvider()
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(),
        XanhSmTransportCostEstimator(),
        route_detail_provider=provider,
        solver_config=FAST_CONFIG,
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "input": ItineraryPlannerInput.model_validate(
                    payload(places=places, foods=foods)
                )
            }
        )
    )

    output = result["output"]
    assert len(provider.calls) == len(result["optimization_result"].selected_arcs)
    assert all(leg.geometry_available for leg in output.days[0].legs)
    assert (
        sum(day.cost_per_person for day in output.days) == output.total_cost_per_person
    )
    breakdown = output.days[0].cost_breakdown
    assert breakdown.total == output.days[0].cost_per_person
    assert breakdown.food == sum(
        stop.cost_per_person for stop in output.days[0].stops if stop.kind == "food"
    )
    assert breakdown.activities == sum(
        stop.cost_per_person for stop in output.days[0].stops if stop.kind == "place"
    )
    assert breakdown.local_transport > 0
    assert sum(leg.cost_per_person for leg in output.days[0].legs) == (
        breakdown.local_transport
    )
    assert breakdown.accommodation == 0
    assert breakdown.misc == 0
    assert output.unscheduled == []
    lake = next(stop for stop in output.days[0].stops if stop.place_id == "lake")
    assert lake.image_urls == ["https://example.test/lake.jpg"]
    assert lake.rating == 4.7
    assert lake.review_count == 100
    assert lake.item_id == "planner:1:lake"
    assert lake.notes is not None
    assert lake.notes.source_type == "url"
    assert lake.personal_notes is None
    assert {
        day: [interval.model_dump(by_alias=True) for interval in intervals or []]
        for day, intervals in (lake.opening_hours or {}).items()
    } == {
        "1": [{"startMinute": 480, "endMinute": 1020}]
    }
    assert [item.period for item in output.source_mix] == ["morning", "evening"]


def test_phase5_adds_selected_accommodation_to_daily_and_total_cost() -> None:
    raw = payload(
        days=2,
        places=[
            candidate("lake", priority="user_input"),
            *continuity_candidates(2),
        ],
        foods=meal_candidates(2),
    )
    raw["accommodations"] = [
        {
            "placeId": "hotel:priced",
            "name": "Priced Hotel",
            "coordinates": {"latitude": 21.03, "longitude": 105.84},
            "address": "Hanoi",
            "rating": 4.5,
            "reviewCount": 100,
            "pricePerNight": {"cost": 600_000, "currency": "VND"},
        }
    ]
    route_provider = GeneratedRouteDetailProvider()
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(),
        XanhSmTransportCostEstimator(),
        route_detail_provider=route_provider,
        solver_config=FAST_CONFIG,
    )

    result = asyncio.run(graph.ainvoke({"input": raw}))

    output = result["output"]
    assert output.accommodation is not None
    assert output.accommodation.place_id == "hotel:priced"
    assert output.accommodation_nights == 1
    assert output.days[0].cost_breakdown.accommodation == 300_000
    assert output.days[1].cost_breakdown.accommodation == 0
    assert output.days[0].legs[-1].to_place_id == "hotel:priced"
    assert output.days[1].legs[0].from_place_id == "hotel:priced"
    assert output.days[0].legs[-1].geometry_available
    assert output.days[1].legs[0].geometry_available
    assert len(route_provider.calls) == 2
    assert output.total_cost_per_person == sum(
        day.cost_breakdown.total for day in output.days
    )


def test_phase5_keeps_valid_plan_when_route_geometry_provider_is_missing() -> None:
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(),
        XanhSmTransportCostEstimator(),
        solver_config=FAST_CONFIG,
    )
    raw = payload(
        places=[
            candidate("lake", priority="user_input"),
            *continuity_candidates(),
        ],
        foods=[
            food("breakfast", supported_meals=["breakfast"]),
            food("lunch", supported_meals=["lunch"]),
            food("dinner", supported_meals=["dinner"]),
        ],
    )

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert result.get("error") is None
    assert result["output"].days
    assert any(
        "Route geometry unavailable" in item for item in result["output"].warnings
    )


def test_phase5_reports_unscheduled_priority_and_discards_optional_quietly() -> None:
    closed = {"1": []}
    raw = payload(
        places=[
            candidate("closed_user", priority="user_input", opening_hours=closed),
            candidate("closed_extra", priority="special_near", opening_hours=closed),
            *continuity_candidates(),
        ],
        foods=[
            food("breakfast", supported_meals=["breakfast"]),
            food("lunch", supported_meals=["lunch"]),
            food("dinner", supported_meals=["dinner"]),
        ],
    )
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(),
        XanhSmTransportCostEstimator(),
        solver_config=FAST_CONFIG,
    )

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert [item.place_id for item in result["output"].unscheduled] == ["closed_user"]
    assert result["output"].discarded_optional_count >= 1


def test_phase5_keeps_upstream_excluded_user_input_in_unscheduled() -> None:
    raw = payload(
        places=continuity_candidates(),
        foods=[
            food("breakfast", supported_meals=["breakfast"]),
            food("lunch", supported_meals=["lunch"]),
            food("dinner", supported_meals=["dinner"]),
        ],
    )
    raw["excludedCandidates"] = [
        {
            "placeId": "lake",
            "name": "Hoàn Kiếm Lake",
            "priority": "user_input",
            "reasonCode": "verification_required",
            "message": "The requested place must be verified before planning.",
        }
    ]
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(),
        XanhSmTransportCostEstimator(),
        solver_config=FAST_CONFIG,
    )

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert [
        (item.place_id, item.reason_code) for item in result["output"].unscheduled
    ] == [("lake", "verification_required")]


def test_route_detail_overrun_is_repaired_by_resolving_the_affected_day() -> None:
    raw = payload(
        places=[
            candidate("lake", priority="user_input"),
            *continuity_candidates(),
        ],
        foods=[
            food("breakfast", supported_meals=["breakfast"]),
            food("lunch", supported_meals=["lunch"]),
            food("dinner", supported_meals=["dinner"]),
        ],
    )
    for index, item in enumerate([*raw["places"], *raw["food"]]):
        item["coordinates"] = {
            "latitude": 21.02 + index / 1000,
            "longitude": 105.84,
        }
    planner_input = ItineraryPlannerInput.model_validate(raw)
    problem = prepare_planning_problem(planner_input)
    estimator = XanhSmTransportCostEstimator()
    routing = asyncio.run(
        build_routing_problem(problem, GeneratedMatrixProvider(), estimator)
    )
    baseline = optimize_itinerary(problem, routing, config=FAST_CONFIG)
    stops = {(stop.place_id, stop.day): stop for stop in baseline.scheduled_stops}
    chosen = min(
        baseline.selected_arcs,
        key=lambda arc: (
            stops[(arc.destination_id, arc.day)].start_minute
            - stops[(arc.origin_id, arc.day)].end_minute
            - routing.travel_by_candidate_pair[
                (arc.origin_id, arc.destination_id)
            ].safe_minutes
        ),
    )
    slack = (
        stops[(chosen.destination_id, chosen.day)].start_minute
        - stops[(chosen.origin_id, chosen.day)].end_minute
        - routing.travel_by_candidate_pair[
            (chosen.origin_id, chosen.destination_id)
        ].safe_minutes
    )
    chosen_nodes = (
        routing.candidate_to_matrix_node[chosen.origin_id],
        routing.candidate_to_matrix_node[chosen.destination_id],
    )
    provider = GeneratedRouteDetailProvider(
        duration_by_pair={
            chosen_nodes: (
                routing.travel_by_candidate_pair[
                    (chosen.origin_id, chosen.destination_id)
                ].safe_minutes
                + slack
                + 3
            )
            * 60
        }
    )
    details = asyncio.run(enrich_selected_routes(problem, routing, baseline, provider))

    assert details.repair_days == {1}
    corrected = apply_route_corrections(
        routing, details, estimator, problem.trip.people
    )
    repaired = optimize_itinerary(
        problem,
        corrected,
        config=FAST_CONFIG,
        repair_locks=RepairLocks(baseline, details.repair_days),
    )
    repaired_details = asyncio.run(
        enrich_selected_routes(problem, corrected, repaired, provider)
    )
    assert repaired.user_input_count == baseline.user_input_count
    assert repaired.url_count == baseline.url_count
    assert not invalid_timeline_days(repaired, repaired_details)


@pytest.mark.parametrize("days", [1, 3, 5, 7])
def test_golden_trip_lengths_keep_output_invariants(days: int) -> None:
    graph = build_itinerary_planner_graph(
        GeneratedMatrixProvider(),
        XanhSmTransportCostEstimator(),
        route_detail_provider=GeneratedRouteDetailProvider(),
        solver_config=FAST_CONFIG,
    )
    raw = payload(
        days=days,
        places=[
            candidate("required", priority="user_input"),
            *continuity_candidates(days),
        ],
        foods=meal_candidates(days),
    )

    result = asyncio.run(graph.ainvoke({"input": raw}))

    assert result.get("error") is None
    output = result["output"]
    assert len(output.days) == days
    assert output.total_cost_per_person <= output.budget_per_person
    for day in output.days:
        assert {stop.meal_type for stop in day.stops if stop.meal_type} == {
            "breakfast",
            "lunch",
            "dinner",
        }
        by_id = {stop.place_id: stop for stop in day.stops}
        for current, following in zip(day.stops, day.stops[1:], strict=False):
            assert current.end_minute <= following.start_minute
        for leg in day.legs:
            assert (
                by_id[leg.to_place_id].start_minute
                >= by_id[leg.from_place_id].end_minute + leg.duration_minutes
            )
