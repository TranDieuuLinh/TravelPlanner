import asyncio
from functools import partial
from time import monotonic

from app.modules.itinerary_planner.contract import (
    ItineraryPlannerInput,
    MissingMealSlot,
    PlannerPreflightFailure,
)
from app.modules.itinerary_planner.finalization import finalize_itinerary
from app.modules.itinerary_planner.hybrid import optimize_hybrid_itinerary
from app.modules.itinerary_planner.optimizer import (
    ObjectiveWeights,
    SolverConfig,
    optimize_itinerary,
)
from app.modules.itinerary_planner.optimizer.locks import RepairLocks
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.ports import (
    MatrixCache,
    RouteDetailProvider,
    RoutingMatrixProvider,
)
from app.modules.itinerary_planner.preprocessing import (
    PlanningPreflightError,
    prepare_planning_problem,
)
from app.modules.itinerary_planner.preflight import (
    ProjectedPoolPreflightError,
    validate_routing_connectivity,
)
from app.modules.itinerary_planner.route_enrichment import (
    RouteEnrichmentResult,
    apply_route_corrections,
    enrich_selected_routes,
    invalid_timeline_days,
)
from app.modules.itinerary_planner.routing import build_routing_problem
from app.shared.tools.transport_cost import TransportCostEstimator
from app.shared.observability import traced_call
from app.modules.itinerary_planner.routing_models import RoutingPhaseError
from app.modules.itinerary_planner.state import ItineraryPlannerState


async def prepare_problem_node(state: ItineraryPlannerState) -> dict:
    started = monotonic()
    payload = state["input"]
    if not isinstance(payload, ItineraryPlannerInput):
        payload = ItineraryPlannerInput.model_validate(payload)
    try:
        prepared = prepare_planning_problem(payload)
    except PlanningPreflightError as exc:
        return {
            "error": str(exc),
            "error_code": "missing_meal_coverage",
            "preflight_failure": PlannerPreflightFailure(
                missing=[
                    MissingMealSlot(day=item.day, meal=item.meal)
                    for item in exc.missing_meals
                ]
            ),
        }
    except ProjectedPoolPreflightError as exc:
        return {
            "error": str(exc),
            "error_code": "projected_pool_preflight_failed",
        }
    return {
        "prepared_problem": prepared,
        "warnings": list(prepared.warnings),
        "phase_timings_ms": {"preprocessing": _elapsed_ms(started)},
    }


def create_build_travel_matrix_node(
    provider: RoutingMatrixProvider | None,
    estimator: TransportCostEstimator | None,
    cache: MatrixCache | None,
    *,
    neighbor_limit: int,
    provider_namespace: str,
):
    async def build_travel_matrix(state: ItineraryPlannerState) -> dict:
        if state.get("error") or "prepared_problem" not in state:
            return {}
        started = monotonic()
        try:
            routing_problem = await build_routing_problem(
                state["prepared_problem"],
                provider,
                estimator,
                cache=cache,
                neighbor_limit=neighbor_limit,
                provider_namespace=provider_namespace,
            )
            validate_routing_connectivity(state["prepared_problem"], routing_problem)
        except RoutingPhaseError as exc:
            return {"error": str(exc), "error_code": exc.code.value}
        except ProjectedPoolPreflightError as exc:
            return {
                "error": str(exc),
                "error_code": "routing_connectivity_preflight_failed",
            }
        return {
            "routing_problem": routing_problem,
            "warnings": [*state.get("warnings", []), *routing_problem.warnings],
            "phase_timings_ms": {
                **state.get("phase_timings_ms", {}),
                "routingMatrix": _elapsed_ms(started),
            },
        }

    return build_travel_matrix


def create_optimize_itinerary_node(
    config: SolverConfig,
    weights: ObjectiveWeights,
):
    async def optimize(state: ItineraryPlannerState) -> dict:
        if state.get("error") or "routing_problem" not in state:
            return {}
        started = monotonic()
        try:
            problem = state["prepared_problem"]
            routing = state["routing_problem"]
            result = await traced_call(
                "optimizer.solve",
                lambda: asyncio.to_thread(
                    partial(
                        optimize_hybrid_itinerary,
                        problem,
                        routing,
                        config=config,
                        weights=weights,
                    )
                ),
                kind="tool",
                input_summary={
                    "days": problem.trip.days,
                    "candidateCount": len(problem.candidate_by_id),
                    "arcCount": len(routing.sparse_arcs),
                    "logSearchProgress": config.log_search_progress,
                },
                output_summary=lambda value: {
                    "status": value.status,
                    "selectedCount": len(value.selected_ids),
                    "passCount": len(value.passes),
                    "optimalityProven": value.optimality_proven,
                },
                metadata={
                    "provider": "ortools",
                    "solver": "hybrid_greedy_local_cp_sat",
                },
            )
        except OptimizationError as exc:
            return {
                "error": str(exc),
                "error_code": f"solver_{exc.status.casefold()}",
            }
        return {
            "optimization_result": result,
            "phase_timings_ms": {
                **state.get("phase_timings_ms", {}),
                "optimization": _elapsed_ms(started),
            },
        }

    return optimize


def create_enrich_selected_routes_node(
    provider: RouteDetailProvider | None,
    estimator: TransportCostEstimator | None,
    config: SolverConfig,
    weights: ObjectiveWeights,
):
    async def enrich(state: ItineraryPlannerState) -> dict:
        if state.get("error") or "optimization_result" not in state:
            return {}
        started = monotonic()
        problem = state["prepared_problem"]
        routing = state["routing_problem"]
        optimization = state["optimization_result"]
        details = await enrich_selected_routes(problem, routing, optimization, provider)
        repair_ms = 0
        if details.repair_days:
            if estimator is None:
                return {
                    "error": "Route repair requires a transport cost estimator.",
                    "error_code": "route_repair_cost_not_configured",
                }
            repair_started = monotonic()
            routing = apply_route_corrections(
                routing, details, estimator, problem.trip.people
            )
            try:
                optimization = await asyncio.to_thread(
                    partial(
                        optimize_itinerary,
                        problem,
                        routing,
                        config=config,
                        weights=weights,
                        repair_locks=RepairLocks(
                            state["optimization_result"], details.repair_days
                        ),
                    )
                )
            except OptimizationError as exc:
                return {
                    "error": f"Route repair failed: {exc}",
                    "error_code": f"route_repair_{exc.status.casefold()}",
                }
            repaired = await enrich_selected_routes(
                problem,
                routing,
                optimization,
                provider,
                days=details.repair_days,
            )
            details = _merge_enrichment(details, repaired)
            repair_ms = _elapsed_ms(repair_started)
        invalid_days = invalid_timeline_days(optimization, details)
        if invalid_days:
            return {
                "error": "Route detail still violates the optimized timeline on days: "
                + ", ".join(map(str, sorted(invalid_days))),
                "error_code": "route_detail_timeline_invalid",
            }
        return {
            "routing_problem": routing,
            "optimization_result": optimization,
            "route_details": details,
            "warnings": [*state.get("warnings", []), *details.warnings],
            "phase_timings_ms": {
                **state.get("phase_timings_ms", {}),
                "routeDetail": max(0, _elapsed_ms(started) - repair_ms),
                "repair": repair_ms,
            },
        }

    return enrich


async def finalize_output_node(state: ItineraryPlannerState) -> dict:
    if state.get("error") or "route_details" not in state:
        return {}
    started = monotonic()
    timings = dict(state.get("phase_timings_ms", {}))
    output = finalize_itinerary(
        state["prepared_problem"],
        state["routing_problem"],
        state["optimization_result"],
        state["route_details"],
        state.get("warnings", []),
        timings,
    )
    timings["finalization"] = _elapsed_ms(started)
    timings["total"] = sum(timings.values())
    return {
        "output": output.model_copy(update={"phase_timings_ms": timings}),
        "phase_timings_ms": timings,
    }


def _merge_enrichment(
    original: RouteEnrichmentResult,
    repaired: RouteEnrichmentResult,
) -> RouteEnrichmentResult:
    repaired_days = {leg.day for leg in repaired.legs}
    return RouteEnrichmentResult(
        legs=tuple(
            [leg for leg in original.legs if leg.day not in repaired_days]
            + list(repaired.legs)
        ),
        repair_days=frozenset(),
        actual_minutes_by_pair={
            **original.actual_minutes_by_pair,
            **repaired.actual_minutes_by_pair,
        },
        actual_distance_by_pair={
            **original.actual_distance_by_pair,
            **repaired.actual_distance_by_pair,
        },
        warnings=tuple(dict.fromkeys([*original.warnings, *repaired.warnings])),
    )


def _elapsed_ms(started: float) -> int:
    return round((monotonic() - started) * 1000)
