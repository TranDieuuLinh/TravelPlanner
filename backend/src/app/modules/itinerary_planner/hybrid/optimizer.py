from __future__ import annotations

from dataclasses import replace

from app.modules.itinerary_planner.hybrid.assembly import assemble_hybrid_result
from app.modules.itinerary_planner.hybrid.heuristic import (
    build_day_shortlist,
    full_day_candidate_ids,
)
from app.modules.itinerary_planner.hybrid.projection import (
    project_problem_day,
    project_routing_day,
    remap_day_result,
)
from app.modules.itinerary_planner.optimizer.config import (
    ObjectiveWeights,
    SolverConfig,
)
from app.modules.itinerary_planner.optimizer.hints import InitialSolutionHint
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.optimizer.solver import (
    OptimizationError,
    optimize_itinerary,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem


def optimize_hybrid_itinerary(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    config: SolverConfig | None = None,
    weights: ObjectiveWeights | None = None,
) -> OptimizationResult:
    selected_config = config or SolverConfig()
    selected_weights = weights or ObjectiveWeights()
    food_ids = {item.place_id for item in problem.valid_food}
    used_ids: set[str] = set()
    results: list[OptimizationResult] = []
    for day in range(1, problem.trip.days + 1):
        shortlist = build_day_shortlist(
            problem,
            routing,
            day=day,
            used_ids=frozenset(used_ids),
            quality_max=selected_weights.quality_max,
        )
        try:
            result = _solve_day(
                problem,
                routing,
                day=day,
                candidate_ids=shortlist.candidate_ids,
                hint=InitialSolutionHint(
                    frozenset(shortlist.hinted_order),
                    {1: shortlist.hinted_order},
                ),
                config=selected_config,
                weights=selected_weights,
            )
        except OptimizationError as shortlist_error:
            expanded = full_day_candidate_ids(
                problem,
                day=day,
                used_ids=frozenset(used_ids),
            )
            try:
                if expanded == shortlist.candidate_ids:
                    raise shortlist_error
                result = _solve_day(
                    problem,
                    routing,
                    day=day,
                    candidate_ids=expanded,
                    hint=None,
                    config=selected_config,
                    weights=selected_weights,
                )
            except OptimizationError as expanded_error:
                if (
                    expanded_error.status != "INFEASIBLE"
                    or selected_config.max_inter_stop_wait_minutes is None
                ):
                    raise
                relaxed_config = replace(
                    selected_config,
                    max_inter_stop_wait_minutes=None,
                )
                try:
                    result = _solve_day(
                        problem,
                        routing,
                        day=day,
                        candidate_ids=expanded,
                        hint=None,
                        config=relaxed_config,
                        weights=selected_weights,
                    )
                except OptimizationError as unique_food_error:
                    if unique_food_error.status != "INFEASIBLE":
                        raise
                    reusable_food_candidates = full_day_candidate_ids(
                        problem,
                        day=day,
                        used_ids=frozenset(used_ids - food_ids),
                    )
                    result = _solve_day(
                        problem,
                        routing,
                        day=day,
                        candidate_ids=reusable_food_candidates,
                        hint=None,
                        config=relaxed_config,
                        weights=selected_weights,
                    )
        remapped = remap_day_result(result, day)
        results.append(remapped)
        used_ids.update(remapped.selected_ids)
    return assemble_hybrid_result(problem, routing, results)


def _solve_day(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    day: int,
    candidate_ids: frozenset[str],
    hint: InitialSolutionHint | None,
    config: SolverConfig,
    weights: ObjectiveWeights,
) -> OptimizationResult:
    day_problem = project_problem_day(problem, day=day, candidate_ids=candidate_ids)
    day_routing = project_routing_day(routing, day=day, candidate_ids=candidate_ids)
    return optimize_itinerary(
        day_problem,
        day_routing,
        config=config,
        weights=weights,
        initial_hint=hint,
    )
