from __future__ import annotations

from math import ceil
from time import monotonic

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.optimizer.result import (
    OptimizationResult,
    SelectedRouteArc,
    SolverPassResult,
)


def build_day_result(problem, routing, stops, config: BeamSearchConfig, started):
    ordered = tuple(sorted(stops, key=lambda item: (item.start_minute, item.place_id)))
    selected_arcs = tuple(
        SelectedRouteArc(
            ordered[index].place_id,
            ordered[index + 1].place_id,
            ordered[index].day,
        )
        for index in range(len(ordered) - 1)
    )
    total = sum(ceil(problem.candidate_by_id[stop.place_id].price.cost) for stop in ordered)
    total += sum(
        routing.travel_by_candidate_pair[(arc.origin_id, arc.destination_id)].transport_cost_per_person
        for arc in selected_arcs
    )
    return OptimizationResult(
        status="FEASIBLE",
        optimality_proven=False,
        selected_ids=tuple(stop.place_id for stop in ordered),
        scheduled_stops=ordered,
        selected_arcs=selected_arcs,
        selected_accommodation_id=None,
        accommodation_transfers=(),
        total_cost_per_person=total,
        user_input_count=sum(
            problem.candidate_by_id[stop.place_id].priority.value == "user_input"
            for stop in ordered
        ),
        url_count=sum(
            problem.candidate_by_id[stop.place_id].priority.value == "url"
            for stop in ordered
        ),
        objective_value=0,
        objective_components={},
        objective_policy_version=config.policy_version,
        passes=(
            SolverPassResult(
                "beam_search",
                "FEASIBLE",
                0,
                round((monotonic() - started) * 1000),
                False,
            ),
        ),
        source_mix=(),
    )
