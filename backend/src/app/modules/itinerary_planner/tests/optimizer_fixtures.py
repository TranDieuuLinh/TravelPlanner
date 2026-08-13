import asyncio

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.optimizer import SolverConfig, optimize_itinerary
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.tests.factories import food, payload
from app.modules.itinerary_planner.tests.routing_fakes import GeneratedMatrixProvider


FAST_CONFIG = SolverConfig(
    pass1_timeout_seconds=2,
    pass2_timeout_seconds=2,
    pass3_timeout_seconds=4,
)


def meal_candidates(days: int = 1) -> list[dict]:
    result = []
    for day in range(1, days + 1):
        for index, meal in enumerate(("breakfast", "lunch", "dinner")):
            candidate = food(f"{meal}_{day}", supported_meals=[meal])
            candidate["coordinates"] = {
                "latitude": 21.02 + day / 1000 + index / 10000,
                "longitude": 105.84,
            }
            result.append(candidate)
    return result


def solve_payload(raw: dict):
    prepared = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))
    routing = asyncio.run(
        build_routing_problem(
            prepared,
            GeneratedMatrixProvider(asymmetric=True),
            XanhSmTransportCostEstimator(),
        )
    )
    return optimize_itinerary(prepared, routing, config=FAST_CONFIG), prepared, routing


def base_payload(*, days: int = 1, places: list[dict] | None = None) -> dict:
    return payload(days=days, places=places or [], foods=meal_candidates(days))
