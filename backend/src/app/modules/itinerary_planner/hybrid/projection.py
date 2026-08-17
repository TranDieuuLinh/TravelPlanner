from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import MappingProxyType

from app.modules.itinerary_planner.optimizer.result import (
    OptimizationResult,
    ScheduledStop,
    SelectedRouteArc,
    SolverPassResult,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import (
    RoutingProblem,
    SafeTravel,
    SparseArc,
)


def project_problem_day(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    candidate_ids: frozenset[str],
) -> PreparedPlanningProblem:
    candidates = {
        candidate_id: candidate
        for candidate_id, candidate in problem.candidate_by_id.items()
        if candidate_id in candidate_ids and day in problem.feasible_days[candidate_id]
    }
    places = tuple(item for item in problem.valid_places if item.place_id in candidates)
    food = tuple(item for item in problem.valid_food if item.place_id in candidates)
    feasible_days = {candidate_id: frozenset({1}) for candidate_id in candidates}
    feasible_windows = {
        (candidate_id, 1): problem.feasible_windows[(candidate_id, day)]
        for candidate_id in candidates
    }
    meal_eligibility = {
        (food_id, 1, meal): windows
        for (food_id, meal_day, meal), windows in problem.meal_eligibility.items()
        if food_id in candidates and meal_day == day
    }
    related = {
        candidate_id: frozenset(
            target
            for target in problem.related_by_place[candidate_id]
            if target in candidates
        )
        for candidate_id in candidates
    }
    unknown = {
        candidate_id: frozenset({1})
        for candidate_id, unknown_days in problem.unknown_opening_days.items()
        if candidate_id in candidates and day in unknown_days
    }
    return PreparedPlanningProblem(
        trip=problem.trip.model_copy(
            update={
                "days": 1,
                "start_date": problem.trip.start_date + timedelta(days=day - 1),
            }
        ),
        accommodations=(),
        accommodation_by_id=MappingProxyType({}),
        valid_places=places,
        valid_food=food,
        candidate_by_id=MappingProxyType(candidates),
        feasible_days=MappingProxyType(feasible_days),
        preferred_days=MappingProxyType(
            {candidate_id: frozenset({1}) for candidate_id in candidates}
        ),
        feasible_windows=MappingProxyType(feasible_windows),
        preferred_windows=MappingProxyType(
            {
                candidate_id: problem.preferred_windows[candidate_id]
                for candidate_id in candidates
            }
        ),
        meal_eligibility=MappingProxyType(meal_eligibility),
        related_by_place=MappingProxyType(related),
        unknown_opening_ids=frozenset(unknown),
        unknown_opening_days=MappingProxyType(unknown),
        late_night_eligible_ids=frozenset(
            candidates.keys() & problem.late_night_eligible_ids
        ),
        unscheduled_priority=(),
        discarded_optional=(),
        warnings=(),
        accommodation_nights=0,
        accommodation_cost_per_person_by_id=MappingProxyType({}),
        canonical_place_id_by_candidate_id=MappingProxyType(
            {
                candidate_id: canonical_id
                for candidate_id, canonical_id in (
                    problem.canonical_place_id_by_candidate_id.items()
                )
                if candidate_id in candidates
            }
        ),
    )


def project_routing_day(
    routing: RoutingProblem,
    *,
    day: int,
    candidate_ids: frozenset[str],
) -> RoutingProblem:
    real_arcs = [
        replace(arc, feasible_days=frozenset({1}))
        for arc in routing.sparse_arcs
        if not arc.is_virtual
        and day in arc.feasible_days
        and arc.origin_id in candidate_ids
        and arc.destination_id in candidate_ids
    ]
    zero = SafeTravel(0, 0, 0, 0)
    virtual_arcs = [
        arc
        for candidate_id in sorted(candidate_ids)
        for arc in (
            SparseArc("__start__:1", candidate_id, frozenset({1}), zero),
            SparseArc(candidate_id, "__end__:1", frozenset({1}), zero),
        )
    ]
    return replace(
        routing,
        sparse_arcs=tuple(
            sorted(
                [*real_arcs, *virtual_arcs],
                key=lambda arc: (arc.origin_id, arc.destination_id),
            )
        ),
    )


def remap_day_result(result: OptimizationResult, day: int) -> OptimizationResult:
    return replace(
        result,
        scheduled_stops=tuple(
            ScheduledStop(
                stop.place_id,
                day,
                stop.start_minute,
                stop.end_minute,
                stop.meal_type,
            )
            for stop in result.scheduled_stops
        ),
        selected_arcs=tuple(
            SelectedRouteArc(arc.origin_id, arc.destination_id, day)
            for arc in result.selected_arcs
        ),
        passes=tuple(
            SolverPassResult(
                name=f"day_{day}:{item.name}",
                status=item.status,
                objective_value=item.objective_value,
                wall_time_ms=item.wall_time_ms,
                optimality_proven=item.optimality_proven,
            )
            for item in result.passes
        ),
    )
