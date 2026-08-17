from __future__ import annotations

import asyncio
from functools import partial
from time import monotonic

from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.optimizer import optimize_beam_search
from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.state import ItineraryPlannerState
from app.shared.observability import traced_call


def create_optimize_beam_search_node(config: BeamSearchConfig | None = None):
    selected_config = config or BeamSearchConfig()

    async def optimize(state: ItineraryPlannerState) -> dict:
        if state.get("error") or "routing_problem" not in state:
            return {}
        started = monotonic()
        problem = state["prepared_problem"]
        routing = state["routing_problem"]
        try:
            result = await traced_call(
                "optimizer.beam_search",
                lambda: asyncio.to_thread(
                    partial(
                        optimize_beam_search,
                        problem,
                        routing,
                        config=selected_config,
                    )
                ),
                kind="tool",
                input_summary={
                    "days": problem.trip.days,
                    "candidateCount": len(problem.candidate_by_id),
                    "arcCount": len(routing.sparse_arcs),
                    "beamWidth": selected_config.beam_width,
                },
                output_summary=lambda value: {
                    "status": value.status,
                    "selectedCount": len(value.selected_ids),
                    "optimalityProven": value.optimality_proven,
                },
                metadata={"provider": "beam_search", "solver": "beam_search"},
            )
        except OptimizationError as exc:
            return {"error": str(exc), "error_code": "beam_search_infeasible"}
        except ValueError as exc:
            return {"error": str(exc), "error_code": "beam_search_infeasible"}
        return {
            "optimization_result": result,
            "phase_timings_ms": {
                **state.get("phase_timings_ms", {}),
                "optimization": round((monotonic() - started) * 1000),
            },
        }

    return optimize
