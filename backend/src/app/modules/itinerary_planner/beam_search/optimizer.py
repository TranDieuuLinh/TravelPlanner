from __future__ import annotations

from dataclasses import replace
from time import monotonic

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.constraints import (
    is_restaurant,
    is_travelplace,
    upper_quartile,
)
from app.modules.itinerary_planner.beam_search.day_search import (
    candidate_ids_by_day,
    has_all_meals,
    search_day,
)
from app.modules.itinerary_planner.beam_search.deadline import BeamSearchDeadline
from app.modules.itinerary_planner.beam_search.errors import BeamSearchError
from app.modules.itinerary_planner.beam_search.evaluation import evaluate_plan
from app.modules.itinerary_planner.beam_search.models import (
    DaySearchState,
    PlanSearchState,
)
from app.modules.itinerary_planner.beam_search.pruning import (
    category_sort_key,
    diversity_count,
    plan_sort_key,
    prune_plans,
)
from app.modules.itinerary_planner.beam_search.result_builder import build_day_result
from app.modules.itinerary_planner.contract import CandidatePriority
from app.modules.itinerary_planner.hybrid.assembly import assemble_hybrid_result
from app.modules.itinerary_planner.optimizer.result import OptimizationResult
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem
from app.modules.itinerary_planner.quality import (
    bayesian_adjusted_rating_by_id,
    bayesian_quality_by_id,
)

PRIORITY_VALUES = frozenset({CandidatePriority.user_input, CandidatePriority.url})

# Backward-compatible private alias used by focused unit tests.
_DayState = DaySearchState
__all__ = ["_DayState", "category_sort_key", "optimize_beam_search"]


def optimize_beam_search(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    config: BeamSearchConfig | None = None,
) -> OptimizationResult:
    selected_config = config or BeamSearchConfig()
    started = monotonic()
    deadline = BeamSearchDeadline.start(
        selected_config.resolved_time_limit_seconds(problem.trip.days),
        check_interval=selected_config.deadline_check_interval,
    )
    distance_q3 = upper_quartile(
        travel.distance_meters
        for (origin, destination), travel in routing.travel_by_candidate_pair.items()
        if origin in problem.candidate_by_id
        and destination in problem.candidate_by_id
        and travel.distance_meters > 0
    )
    review_q3 = upper_quartile(
        (
            candidate.review_count
            for candidate in problem.candidate_by_id.values()
            if candidate.review_count is not None
        ),
        quantile=selected_config.review_quantile,
    )
    quality = bayesian_quality_by_id(problem.candidate_by_id.values())
    adjusted_ratings = bayesian_adjusted_rating_by_id(problem.candidate_by_id.values())
    day_search_config = replace(
        selected_config,
        beam_width=(
            max(selected_config.beam_width, selected_config.combination_beam_width)
            if problem.trip.days > 1
            else selected_config.beam_width
        ),
    )
    candidates_by_day = candidate_ids_by_day(problem)
    matrix_node_position = {
        node_id: index for index, node_id in enumerate(routing.matrix.node_ids)
    }
    frontier = [PlanSearchState()]
    fallback_frontier: list[PlanSearchState] = []
    for day in range(1, problem.trip.days + 1):
        if deadline.expired(force=True):
            break
        next_frontier: list[PlanSearchState] = []
        for plan in frontier:
            used_travelplaces = _travelplace_ids(
                problem, tuple(stop for day_stops in plan.days for stop in day_stops)
            )
            day_states = search_day(
                problem,
                routing,
                day=day,
                candidate_ids=candidates_by_day[day],
                matrix_node_position=matrix_node_position,
                used_ids=frozenset(used_travelplaces),
                quality=quality,
                adjusted_ratings=adjusted_ratings,
                distance_q3=distance_q3,
                review_q3=review_q3,
                config=day_search_config,
                deadline=deadline,
            )
            next_frontier.extend(
                _extend_plan(problem, plan, state, selected_config)
                for state in day_states
            )
            if deadline.expired(force=True):
                break
        if next_frontier:
            fallback_frontier = prune_plans(
                next_frontier, selected_config.combination_beam_width, problem
            )
        frontier = prune_plans(
            next_frontier, selected_config.combination_beam_width, problem
        )
        if not frontier:
            break

    if not frontier:
        frontier = fallback_frontier
    if not frontier or not any(plan.days for plan in frontier):
        code = "beam_search_deadline" if deadline.hit else "beam_search_no_candidate"
        raise BeamSearchError(code, "Beam Search found no candidate itinerary.")

    best = max(frontier, key=lambda state: plan_sort_key(state, problem))
    if len(best.days) != problem.trip.days:
        code = (
            "beam_search_deadline"
            if deadline.hit
            else "beam_search_incomplete_days"
        )
        raise BeamSearchError(code, "Beam Search did not schedule every trip day.")
    day_results = tuple(
        build_day_result(problem, routing, stops, selected_config, started)
        for stops in best.days
    )
    result = assemble_hybrid_result(problem, routing, day_results)
    complete = len(best.days) == problem.trip.days and all(
        has_all_meals(
            DaySearchState(
                stops=stops,
                meal_starts=tuple(
                    (stop.meal_type, stop.start_minute)
                    for stop in stops
                    if stop.meal_type is not None
                ),
            )
        )
        for stops in best.days
    )
    result = replace(
        result,
        status="FEASIBLE" if complete else "PARTIAL",
        objective_value=round(best.score),
        objective_components={
            "beam_score": round(best.score),
            "restaurant_coverage": sum(
                is_restaurant(problem.candidate_by_id[item])
                for item in best.selected_ids
            ),
            "beam_transition_checks": deadline.transition_count,
            "beam_deadline_hit": int(deadline.hit),
        },
        objective_policy_version=selected_config.policy_version,
        optimality_proven=False,
        evaluation=evaluate_plan(problem, routing, result),
    )
    return result


def _extend_plan(
    problem, plan: PlanSearchState, state: DaySearchState, config
) -> PlanSearchState:
    return PlanSearchState(
        days=(*plan.days, state.stops),
        selected_ids=plan.selected_ids | state.selected_ids,
        priority_ids=plan.priority_ids | state.priority_ids,
        score=(
            plan.score
            + state.score
            + config.weights.travelplace_final_weight * state.travelplace_count
        ),
        cost=plan.cost + state.cost,
        restaurant_count=plan.restaurant_count + state.restaurant_count,
        travelplace_count=plan.travelplace_count + state.travelplace_count,
        drink_dessert_count=plan.drink_dessert_count + state.drink_dessert_count,
        entertainment_count=plan.entertainment_count + state.entertainment_count,
        diversity_count=plan.diversity_count + diversity_count(problem, state.stops),
    )


def _travelplace_ids(problem, stops):
    return {
        stop.place_id
        for stop in stops
        if is_travelplace(problem.candidate_by_id[stop.place_id])
    }
