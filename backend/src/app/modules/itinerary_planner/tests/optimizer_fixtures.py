import asyncio

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.optimizer import SolverConfig, optimize_itinerary
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.routing_fakes import GeneratedMatrixProvider

FAST_CONFIG = SolverConfig(
    priority_timeout_seconds=2,
    utility_timeout_seconds=4,
    utility_parallel_workers=1,
    max_utility_no_improvement_rounds=0,
)


def meal_candidates(days: int = 1) -> list[dict]:
    result = []
    for day in range(1, days + 1):
        for meal in ("breakfast", "lunch", "dinner"):
            opening_hours = {str(item_day): [] for item_day in range(1, days + 1)}
            opening_hours[str(day)] = [{"startMinute": 480, "endMinute": 1230}]
            candidate = food(
                f"{meal}_{day}",
                supported_meals=[meal],
                opening_hours=opening_hours,
            )
            result.append(candidate)
    return result


def continuity_candidates(days: int = 1) -> list[dict]:
    result = []
    for day in range(1, days + 1):
        for index, duration in enumerate((30, 60, 90, 120, 150, 180), start=1):
            opening_hours = {str(item_day): [] for item_day in range(1, days + 1)}
            opening_hours[str(day)] = [{"startMinute": 480, "endMinute": 1380}]
            item = candidate(
                f"continuity_{day}_{index}",
                priority="special_near",
                duration_minutes=duration,
                opening_hours=opening_hours,
            )
            item["tags"] = []
            item["rating"] = None
            item["reviewCount"] = None
            item["sourceKind"] = "generic"
            result.append(item)
    return result


def solve_payload(raw: dict, *, matrix_provider=None, config: SolverConfig = FAST_CONFIG):
    prepared = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))
    routing = asyncio.run(
        build_routing_problem(
            prepared,
            matrix_provider or GeneratedMatrixProvider(asymmetric=True),
            XanhSmTransportCostEstimator(),
        )
    )
    return optimize_itinerary(prepared, routing, config=config), prepared, routing


def base_payload(*, days: int = 1, places: list[dict] | None = None) -> dict:
    return payload(
        days=days,
        places=[*(places or []), *continuity_candidates(days)],
        foods=meal_candidates(days),
    )
