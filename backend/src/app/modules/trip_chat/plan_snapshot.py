from typing import Any


def update_stop_personal_notes(
    output: dict[str, Any] | None,
    *,
    day: int,
    item_id: str,
    personal_notes: str | None,
) -> bool:
    """Update only the user-owned note in a planner JSON snapshot."""

    if not isinstance(output, dict):
        return False
    for raw_day in output.get("days", []):
        if not isinstance(raw_day, dict) or raw_day.get("day") != day:
            continue
        for index, stop in enumerate(raw_day.get("stops", [])):
            if not isinstance(stop, dict):
                continue
            legacy_id = f"planner-{day}-{index + 1}-{stop.get('placeId', '')}"
            if stop.get("itemId") == item_id or legacy_id == item_id:
                stop["personalNotes"] = personal_notes
                return True
    return False
