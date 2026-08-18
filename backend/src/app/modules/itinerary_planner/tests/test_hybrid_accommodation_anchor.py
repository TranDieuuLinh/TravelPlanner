import asyncio

import pytest

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.hybrid import optimize_hybrid_itinerary
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    FAST_CONFIG,
    base_payload,
)
from app.modules.itinerary_planner.tests.routing_fakes import GeneratedMatrixProvider


def _problem_with_accommodations(accommodations: list[dict]):
    raw = base_payload(days=2)
    raw["accommodations"] = accommodations
    problem = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))
    routing = asyncio.run(
        build_routing_problem(
            problem,
            GeneratedMatrixProvider(asymmetric=True),
            XanhSmTransportCostEstimator(),
        )
    )
    return problem, routing


def test_hybrid_anchors_every_day_to_the_top_accommodation() -> None:
    problem, routing = _problem_with_accommodations(
        [
            {
                "placeId": "hotel:top",
                "name": "Top Hotel",
                "coordinates": {"latitude": 21.02, "longitude": 105.84},
                "pricePerNight": {"cost": 900_000, "currency": "VND"},
            },
            {
                "placeId": "hotel:cheaper",
                "name": "Cheaper Hotel",
                "coordinates": {"latitude": 21.02, "longitude": 105.84},
                "pricePerNight": {"cost": 100_000, "currency": "VND"},
            },
        ]
    )

    result = optimize_hybrid_itinerary(problem, routing, config=FAST_CONFIG)

    assert result.selected_accommodation_id == "hotel:top"
    assert {(item.day, item.direction) for item in result.accommodation_transfers} == {
        (1, "end"),
        (2, "start"),
    }
    day_1_last = max(
        (stop for stop in result.scheduled_stops if stop.day == 1),
        key=lambda stop: stop.end_minute,
    )
    day_2_first = min(
        (stop for stop in result.scheduled_stops if stop.day == 2),
        key=lambda stop: stop.start_minute,
    )
    return_minutes = routing.travel_by_candidate_pair[
        (day_1_last.place_id, "hotel:top")
    ].safe_minutes
    departure_minutes = routing.travel_by_candidate_pair[
        ("hotel:top", day_2_first.place_id)
    ].safe_minutes
    assert (
        day_2_first.start_minute
        - departure_minutes
        + 1440
        - day_1_last.end_minute
        - return_minutes
        >= 7 * 60
    )


def test_hybrid_reports_top_accommodation_anchor_connectivity_failure() -> None:
    problem, routing = _problem_with_accommodations(
        [
            {
                "placeId": "hotel:top",
                "name": "Top Hotel",
                "coordinates": {"latitude": 21.02, "longitude": 105.84},
                "pricePerNight": {"cost": 300_000, "currency": "VND"},
            }
        ]
    )
    reachable_without_hotel = {
        pair: travel
        for pair, travel in routing.travel_by_candidate_pair.items()
        if "hotel:top" not in pair
    }
    routing.travel_by_candidate_pair.clear()
    routing.travel_by_candidate_pair.update(reachable_without_hotel)

    with pytest.raises(
        OptimizationError,
        match="Top accommodation hotel:top could not anchor day 1",
    ):
        optimize_hybrid_itinerary(problem, routing, config=FAST_CONFIG)
