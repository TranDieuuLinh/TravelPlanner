from __future__ import annotations

from typing import Any


def update_day_costs(
    output: dict[str, Any],
    raw_day: dict[str, Any],
    stops: list[dict[str, Any]],
    legs: list[dict[str, Any]],
) -> None:
    breakdown = raw_day.setdefault("costBreakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = raw_day["costBreakdown"] = {}
    previous_total = int(raw_day.get("costPerPerson") or breakdown.get("total") or 0)
    food = sum(
        int(item.get("costPerPerson") or 0)
        for item in stops
        if item.get("kind") == "food"
    )
    activities = sum(
        int(item.get("costPerPerson") or 0)
        for item in stops
        if item.get("kind") != "food"
    )
    transport = sum(int(item.get("costPerPerson") or 0) for item in legs)
    accommodation = int(breakdown.get("accommodation") or 0)
    misc = int(breakdown.get("misc") or 0)
    total = accommodation + food + transport + activities + misc
    breakdown.update(
        {
            "accommodation": accommodation,
            "food": food,
            "localTransport": transport,
            "activities": activities,
            "misc": misc,
            "total": total,
            "currency": breakdown.get("currency")
            or output.get("currency")
            or "VND",
        }
    )
    raw_day["costPerPerson"] = total
    if isinstance(output.get("totalCostPerPerson"), (int, float)):
        output["totalCostPerPerson"] = max(
            0,
            round(float(output["totalCostPerPerson"]) - previous_total + total),
        )
