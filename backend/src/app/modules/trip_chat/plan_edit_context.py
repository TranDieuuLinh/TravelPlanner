from copy import deepcopy
from typing import Any


def compatible_plan_item_id(
    day: int,
    index: int,
    stop: dict[str, Any],
) -> str:
    return str(
        stop.get("itemId")
        or f"planner-{day}-{index + 1}-{stop.get('placeId', '')}"
    )


def planner_output_for_edit_context(
    output: dict[str, Any],
) -> dict[str, Any]:
    """Project legacy stops with the same compatible IDs mutations accept."""
    projected = deepcopy(output)
    for raw_day in projected.get("days", []):
        if not isinstance(raw_day, dict) or not isinstance(raw_day.get("day"), int):
            continue
        for index, stop in enumerate(raw_day.get("stops", [])):
            if isinstance(stop, dict):
                stop["itemId"] = compatible_plan_item_id(raw_day["day"], index, stop)
    return projected
