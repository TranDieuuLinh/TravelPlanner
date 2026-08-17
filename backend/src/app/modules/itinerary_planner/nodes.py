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
from app.modules.itinerary_planner.optimizer.hints import hint_from_result
from app.modules.itinerary_planner.optimizer.locks import RepairLocks
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.ports import (
    MatrixCache,
    RouteDetailProvider,
    RoutingMatrixProvider,
)
from app.modules.itinerary_planner.preflight import (
    ProjectedPoolPreflightError,
    validate_routing_connectivity,
)
from app.modules.itinerary_planner.preprocessing import (
    PlanningPreflightError,
    prepare_planning_problem,
)
from app.modules.itinerary_planner.route_enrichment import (
    RouteEnrichmentResult,
    apply_route_corrections,
    enrich_selected_routes,
    invalid_timeline_days,
    route_correction_pairs,
)
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.routing_models import RoutingPhaseError
from app.modules.itinerary_planner.state import ItineraryPlannerState
from app.modules.itinerary_planner.timeline_reflow import try_reflow_timeline
from app.shared.observability import traced_call
from app.shared.tools.transport_cost import TransportCostEstimator


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
    *,
    beam_mode: bool = False,
):
    async def enrich(state: ItineraryPlannerState) -> dict:
        if state.get("error") or "optimization_result" not in state:
            return {}
        started = monotonic()
        problem = state["prepared_problem"]
        routing = state["routing_problem"]
        optimization = state["optimization_result"]
        detail_cache = {}
        details = await enrich_selected_routes(
            problem,
            routing,
            optimization,
            provider,
            detail_cache=detail_cache,
        )
        repair_ms = 0
        if details.repair_days:
            if estimator is None:
                return {
                    "error": "Route repair requires a transport cost estimator.",
                    "error_code": "route_repair_cost_not_configured",
                }
            repair_started = monotonic()
            while details.repair_days:
                repair_days = details.repair_days
                if not route_correction_pairs(routing, details):
                    return {
                        "error": "Route repair stopped because no new travel-time "
                        "correction was available.",
                        "error_code": "route_repair_no_progress",
                    }
                routing = apply_route_corrections(
                    routing, details, estimator, problem.trip.people
                )
                reflowed = try_reflow_timeline(
                    problem,
                    routing,
                    optimization,
                    repair_days,
                    weights,
                    max_inter_stop_wait_minutes=config.max_inter_stop_wait_minutes,
                )
                if reflowed is not None:
                    optimization = reflowed
                    repair_scope = repair_days
                    repair_warning = (
                        "Route detail changed travel time; affected-day timelines "
                        "were shifted without changing selected places or route order."
                    )
                else:
                    if beam_mode:
                        return {
                            "error": "Beam Search route detail could not reflow the selected timeline.",
                            "error_code": "beam_route_reflow_failed",
                        }
                    try:
                        optimization, repair_scope, repair_warning = (
                            await _repair_optimization(
                                problem,
                                routing,
                                optimization,
                                repair_days,
                                config,
                                weights,
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
                    days=repair_scope,
                    detail_cache=detail_cache,
                )
                details = _merge_enrichment(details, repaired)
                if repair_warning:
                    details = RouteEnrichmentResult(
                        details.legs,
                        details.repair_days,
                        details.actual_minutes_by_pair,
                        details.actual_distance_by_pair,
                        (*details.warnings, repair_warning),
                    )
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


async def _repair_optimization(
    problem,
    routing,
    baseline,
    affected_days: frozenset[int],
    config: SolverConfig,
    weights: ObjectiveWeights,
) -> tuple[OptimizationResult, frozenset[int], str | None]:
    try:
        repaired = await asyncio.to_thread(
            partial(
                optimize_itinerary,
                problem,
                routing,
                config=config,
                weights=weights,
                repair_locks=RepairLocks(baseline, affected_days),
                initial_hint=hint_from_result(baseline),
            )
        )
        return repaired, affected_days, None
    except OptimizationError as exc:
        if exc.status not in {"INFEASIBLE", "UNKNOWN"}:
            raise
    repaired = await asyncio.to_thread(
        partial(
            optimize_hybrid_itinerary,
            problem,
            routing,
            config=config,
            weights=weights,
        )
    )
    return (
        repaired,
        frozenset(range(1, problem.trip.days + 1)),
        (
            "Route repair relaxed unaffected-day locks after the locked solve could not "
            "produce a feasible result, then replanned compact per-day candidate pools."
        ),
    )


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
        repair_days=repaired.repair_days,
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
