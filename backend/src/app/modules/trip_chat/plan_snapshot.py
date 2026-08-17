from typing import Any


def _remove_accommodation_cost(output: dict[str, Any]) -> None:
    removed_total = 0.0
    for raw_day in output.get("days", []):
        if not isinstance(raw_day, dict):
            continue
        breakdown = raw_day.get("costBreakdown")
        if not isinstance(breakdown, dict):
            continue
        accommodation_cost = breakdown.get("accommodation")
        if not isinstance(accommodation_cost, (int, float)):
            continue
        removed_total += accommodation_cost
        breakdown["accommodation"] = 0
        if isinstance(breakdown.get("total"), (int, float)):
            breakdown["total"] = max(0, breakdown["total"] - accommodation_cost)
        if isinstance(raw_day.get("costPerPerson"), (int, float)):
            raw_day["costPerPerson"] = max(
                0, raw_day["costPerPerson"] - accommodation_cost
            )
    if isinstance(output.get("totalCostPerPerson"), (int, float)):
        output["totalCostPerPerson"] = max(
            0, output["totalCostPerPerson"] - removed_total
        )


def update_accommodation(
    output: dict[str, Any] | None,
    *,
    changes: dict[str, Any],
) -> bool:
    """Update user-editable accommodation fields and linked route identifiers."""

    if not isinstance(output, dict) or not isinstance(output.get("accommodation"), dict):
        return False
    accommodation = output["accommodation"]
    old_place_id = accommodation.get("placeId")
    new_place_id = changes.get("placeId", old_place_id)
    for key, value in changes.items():
        if key in {"latitude", "longitude"}:
            coordinates = accommodation.setdefault("coordinates", {})
            if isinstance(coordinates, dict):
                coordinates[key] = value
        else:
            accommodation[key] = value
    if old_place_id != new_place_id:
        for raw_day in output.get("days", []):
            if not isinstance(raw_day, dict):
                continue
            for leg in raw_day.get("legs", []):
                if not isinstance(leg, dict):
                    continue
                if leg.get("fromPlaceId") == old_place_id:
                    leg["fromPlaceId"] = new_place_id
                if leg.get("toPlaceId") == old_place_id:
                    leg["toPlaceId"] = new_place_id
    return True


def delete_accommodation(output: dict[str, Any] | None) -> bool:
    """Remove accommodation, its transfer legs, and its priced contribution."""

    if not isinstance(output, dict) or not isinstance(output.get("accommodation"), dict):
        return False
    place_id = output["accommodation"].get("placeId")
    for raw_day in output.get("days", []):
        if not isinstance(raw_day, dict):
            continue
        legs = raw_day.get("legs")
        if isinstance(legs, list):
            raw_day["legs"] = [
                leg
                for leg in legs
                if not isinstance(leg, dict)
                or (
                    leg.get("fromPlaceId") != place_id
                    and leg.get("toPlaceId") != place_id
                )
            ]
    _remove_accommodation_cost(output)
    output["accommodation"] = None
    output["accommodationNights"] = 0
    return True


def select_transport_option(
    output: dict[str, Any] | None,
    *,
    day: int,
    leg_index: int,
    selection: dict[str, Any],
) -> str:
    """Persist a normalized user transport choice on one planner leg."""

    if not isinstance(output, dict):
        return "day_not_found"
    raw_day = next(
        (
            candidate
            for candidate in output.get("days", [])
            if isinstance(candidate, dict) and candidate.get("day") == day
        ),
        None,
    )
    if raw_day is None:
        return "day_not_found"
    legs = raw_day.get("legs")
    if not isinstance(legs, list) or leg_index < 0 or leg_index >= len(legs):
        return "leg_not_found"
    leg = legs[leg_index]
    if not isinstance(leg, dict):
        return "leg_not_found"
    leg["selectedTransport"] = selection
    return "updated"


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
