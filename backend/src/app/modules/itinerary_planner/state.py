from typing import TypedDict

from app.modules.itinerary_planner.contract import (
    ItineraryPlannerInput,
    PlannerPreflightFailure,
)
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.output_contract import ItineraryPlannerOutput
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.route_enrichment import RouteEnrichmentResult
from app.modules.itinerary_planner.routing_models import RoutingProblem


class ItineraryPlannerState(TypedDict, total=False):
    input: ItineraryPlannerInput
    prepared_problem: PreparedPlanningProblem
    routing_problem: RoutingProblem
    optimization_result: OptimizationResult
    route_details: RouteEnrichmentResult
    output: ItineraryPlannerOutput
    warnings: list[str]
    phase_timings_ms: dict[str, int]
    error: str
    error_code: str
    preflight_failure: PlannerPreflightFailure
    beam_failure_reason: str
    beam_failure_message: str
    cp_sat_failure_reason: str
    cp_sat_failure_message: str
    selected_optimizer: str
    fallback_used: bool
