from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.output_contract import ItineraryPlannerOutput


class BeamFirstFallbackPlanner:
    """Run Beam Search first and use the existing planner on failure."""

    def __init__(self, beam_graph: Any, fallback_graph: Any) -> None:
        self._beam_graph = beam_graph
        self._fallback_graph = fallback_graph

    async def ainvoke(self, payload: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        try:
            beam_result = await self._beam_graph.ainvoke(payload, **kwargs)
        except Exception:
            return await self._run_fallback(payload, kwargs, "beam_exception")

        reason = _beam_failure_reason(payload, beam_result)
        if reason is None:
            return beam_result
        if reason in {
            "missing_meal_coverage",
            "projected_pool_preflight_failed",
            "routing_connectivity_preflight_failed",
        }:
            return beam_result
        return await self._run_fallback(payload, kwargs, reason)

    async def _run_fallback(
        self,
        payload: Mapping[str, Any],
        kwargs: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        result = await self._fallback_graph.ainvoke(payload, **kwargs)
        warning = (
            "Beam Search was not used successfully ("
            f"{reason}); Hybrid planner was used as fallback."
        )
        warnings = [*result.get("warnings", []), warning]
        output = result.get("output")
        if isinstance(output, ItineraryPlannerOutput):
            output = output.model_copy(
                update={"warnings": [*output.warnings, warning]}
            )
        elif isinstance(output, Mapping):
            output = {**output, "warnings": [*output.get("warnings", []), warning]}
        return {**result, "output": output, "warnings": warnings}


def _beam_failure_reason(
    payload: Mapping[str, Any], result: Mapping[str, Any]
) -> str | None:
    if result.get("error"):
        return str(result.get("error_code") or "beam_error")
    output = result.get("output")
    if output is None:
        return "beam_output_missing"
    try:
        planner_input = _planner_input(payload)
        validated_output = (
            output
            if isinstance(output, ItineraryPlannerOutput)
            else ItineraryPlannerOutput.model_validate(output)
        )
    except Exception:
        return "beam_output_invalid"
    if validated_output.solver.status != "FEASIBLE":
        return f"beam_status_{validated_output.solver.status.casefold()}"
    if len(validated_output.days) != planner_input.trip.days:
        return "beam_incomplete_days"
    if any(not day.stops for day in validated_output.days):
        return "beam_empty_day"
    return None


def _planner_input(payload: Mapping[str, Any]) -> ItineraryPlannerInput:
    value = payload.get("input", payload)
    if isinstance(value, ItineraryPlannerInput):
        return value
    return ItineraryPlannerInput.model_validate(value)
