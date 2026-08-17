from __future__ import annotations

from collections import Counter
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
from app.modules.itinerary_planner.optimizer.tag_diversity import meaningful_tags
from app.modules.itinerary_planner.optimizer.solver import (
    OptimizationError,
    optimize_itinerary,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem

ACTIVITY_FILL_TARGET_PER_DAY = 3
REFILL_ACTIVITY_CANDIDATE_LIMIT = 4


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
    trip_tag_counts: Counter[str] = Counter()
    results: list[OptimizationResult] = []
    for day in range(1, problem.trip.days + 1):
        shortlist = build_day_shortlist(
            problem,
            routing,
            day=day,
            used_ids=frozenset(used_ids),
            quality_max=selected_weights.quality_max,
            trip_tag_counts=trip_tag_counts,
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
        except OptimizationError:
            expanded = full_day_candidate_ids(
                problem,
                day=day,
                used_ids=frozenset(used_ids),
            )
            try:
                if expanded == shortlist.candidate_ids:
                    raise
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
        selected_activity_count = _selected_activity_count(result, problem)
        if selected_activity_count < ACTIVITY_FILL_TARGET_PER_DAY:
            refill_candidates = _bounded_refill_candidate_ids(
                problem,
                routing,
                day=day,
                used_ids=frozenset(used_ids),
                shortlist_ids=shortlist.candidate_ids,
                selected_ids=frozenset(result.selected_ids),
                trip_tag_counts=trip_tag_counts,
            )
            if refill_candidates != shortlist.candidate_ids:
                try:
                    refill = _solve_day(
                        problem,
                        routing,
                        day=day,
                        candidate_ids=refill_candidates,
                        hint=None,
                        config=selected_config,
                        weights=selected_weights,
                    )
                except OptimizationError:
                    refill = None
                if (
                    refill is not None
                    and _selected_activity_count(refill, problem)
                    > selected_activity_count
                ):
                    result = refill
        remapped = remap_day_result(result, day)
        results.append(remapped)
        _update_trip_tag_counts(trip_tag_counts, remapped, problem, food_ids)
        used_ids.update(remapped.selected_ids)
    return assemble_hybrid_result(problem, routing, results)


def _selected_activity_count(
    result: OptimizationResult,
    problem: PreparedPlanningProblem,
) -> int:
    place_ids = {item.place_id for item in problem.valid_places}
    return sum(candidate_id in place_ids for candidate_id in result.selected_ids)


def _bounded_refill_candidate_ids(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    shortlist_ids: frozenset[str],
    selected_ids: frozenset[str],
    trip_tag_counts: Counter[str],
) -> frozenset[str]:
    """Add a few flexible, nearby reserve activities without a full-pool solve."""
    place_ids = {item.place_id for item in problem.valid_places}
    reserve_ids = [
        candidate_id
        for candidate_id, feasible_days in problem.feasible_days.items()
        if day in feasible_days
        and candidate_id not in used_ids
        and candidate_id not in shortlist_ids
        and candidate_id in place_ids
    ]

    def rank(candidate_id: str) -> tuple[int, int, int, str]:
        candidate = problem.candidate_by_id[candidate_id]
        groups = meaningful_tags(candidate.tags)
        repeated_groups = (
            0
            if groups and any(not trip_tag_counts.get(tag, 0) for tag in groups)
            else max(1, sum(trip_tag_counts.get(tag, 0) for tag in groups))
        )
        flexibility = sum(
            max(0, window.duration_minutes - candidate.duration_minutes)
            for window in problem.feasible_windows[(candidate_id, day)]
        )
        nearby = min(
            (
                routing.travel_by_candidate_pair[
                    (candidate_id, selected_id)
                ].safe_minutes
                for selected_id in selected_ids
                if (candidate_id, selected_id) in routing.travel_by_candidate_pair
            ),
            default=10**6,
        )
        return (repeated_groups, nearby, -flexibility, candidate_id)

    additions = sorted(reserve_ids, key=rank)[:REFILL_ACTIVITY_CANDIDATE_LIMIT]
    return frozenset([*shortlist_ids, *additions])


def _update_trip_tag_counts(
    counts: Counter[str],
    result: OptimizationResult,
    problem: PreparedPlanningProblem,
    food_ids: set[str],
) -> None:
    for candidate_id in result.selected_ids:
        if candidate_id in food_ids:
            continue
        candidate = problem.candidate_by_id.get(candidate_id)
        if candidate is not None:
            counts.update(meaningful_tags(candidate.tags))


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
