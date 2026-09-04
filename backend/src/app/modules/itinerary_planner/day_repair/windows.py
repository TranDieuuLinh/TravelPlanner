from __future__ import annotations

import re
from typing import Any

from app.modules.itinerary_planner.policies import (
    ITINERARY_START_MINUTE,
    OVERNIGHT_END_MINUTE,
    STANDARD_DAY_END_MINUTE,
)


def start_ranges(
    stop: dict[str, Any], day: int, duration: int
) -> tuple[tuple[int, int], ...]:
    opening = stop.get("openingHours")
    if opening is None or not isinstance(opening, dict):
        return ((ITINERARY_START_MINUTE, STANDARD_DAY_END_MINUTE - duration),)
    intervals = opening.get(str(day))
    if intervals is None:
        return ((ITINERARY_START_MINUTE, STANDARD_DAY_END_MINUTE - duration),)
    ranges: list[tuple[int, int]] = []
    for interval in intervals:
        if not isinstance(interval, dict):
            continue
        try:
            start = int(interval["startMinute"])
            end = int(interval["endMinute"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            end += 1440
        upper = min(OVERNIGHT_END_MINUTE, end) - duration
        if start <= upper:
            ranges.append((max(0, start), upper))
    return tuple(sorted(ranges))


def intersect_ranges(
    ranges: tuple[tuple[int, int], ...], lower: int, upper: int
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (max(start, lower), min(end, upper))
        for start, end in ranges
        if max(start, lower) <= min(end, upper)
    )


def parse_opening_hours(value: Any) -> list[dict[str, int]] | None:
    if value is None or not isinstance(value, list):
        return None
    intervals: list[dict[str, int]] = []
    for raw in value:
        match = re.fullmatch(
            r"\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*",
            str(raw),
        )
        if not match:
            continue
        start = int(match.group(1)) * 60 + int(match.group(2))
        end = int(match.group(3)) * 60 + int(match.group(4))
        intervals.append({"startMinute": start, "endMinute": end})
    return intervals or None
