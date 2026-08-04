"""Helpers for the new ``places.opening_hours`` JSON shape.

The Google-derived schema writes ``places.opening_hours`` as::

    [
        {"dayOfWeek": 1, "dayName": "monday",
         "rawTimeSlots": "06:00-12:00, 14:00-22:00",
         "is24Hours": false},
        ...
    ]

But legacy fixtures and a handful of business rules still pass the older
``{openTime, closeTime, is24Hours}`` objects. Both shapes are supported
here so callers can stay agnostic when migrating.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.modules.plans.place_selector.time_windows import parse_unbounded_clock_minutes


_SLOT_SEPARATOR = re.compile(r"\s*(?:,|;|\||/|\n|\t| và )\s*")
_RANGE_SEPARATOR = re.compile(r"\s*[-–—~]\s*")


def extract_time_intervals(
    opening_hours: Iterable[dict] | None,
) -> list[tuple[int, int]]:
    """Return the open/close intervals (minutes since midnight) for one day entry.

    Handles both legacy (``openTime``/``closeTime``) and new
    (``rawTimeSlots``) payloads. The ``rawTimeSlots`` string may contain
    multiple ranges separated by commas, semicolons, pipes, newlines or
    ``" và "`` (Vietnamese). Ranges are assumed to be on the same day
    unless the close value is smaller than the open value, in which case
    it is interpreted as an overnight shift that ends the next day.
    """

    intervals: list[tuple[int, int]] = []
    if not opening_hours:
        return intervals

    for entry in opening_hours:
        if not isinstance(entry, dict):
            continue
        if entry.get("is24Hours"):
            intervals.append((0, 24 * 60))
            continue

        for start, end in _intervals_from_entry(entry):
            if end <= start:
                end += 24 * 60
            intervals.append((start, end))

    return intervals


def _intervals_from_entry(entry: dict) -> list[tuple[int, int]]:
    raw_slots = entry.get("rawTimeSlots")
    if isinstance(raw_slots, str) and raw_slots.strip():
        result: list[tuple[int, int]] = []
        for chunk in _SLOT_SEPARATOR.split(raw_slots):
            interval = _parse_range(chunk)
            if interval is not None:
                result.append(interval)
        if result:
            return result

    open_value = entry.get("openTime") or entry.get("open_time")
    close_value = entry.get("closeTime") or entry.get("close_time")
    interval = _parse_pair(open_value, close_value)
    if interval is not None:
        return [interval]
    return []


def _parse_range(chunk: str) -> tuple[int, int] | None:
    chunk = chunk.strip()
    if not chunk:
        return None
    if "-" not in chunk and "–" not in chunk and "—" not in chunk and "~" not in chunk:
        return None
    parts = _RANGE_SEPARATOR.split(chunk, maxsplit=1)
    if len(parts) != 2:
        return None
    return _parse_pair(parts[0], parts[1])


def _parse_pair(open_value: object, close_value: object) -> tuple[int, int] | None:
    if not isinstance(open_value, str) or not isinstance(close_value, str):
        return None
    start = parse_unbounded_clock_minutes(open_value)
    end = parse_unbounded_clock_minutes(close_value)
    if start is None or end is None:
        return None
    return start, end


def is_24_hours(opening_hours: Iterable[dict] | None) -> bool:
    """Return ``True`` when every entry is a 24-hour shift."""

    if not opening_hours:
        return False
    return all(
        isinstance(entry, dict) and entry.get("is24Hours") for entry in opening_hours
    )


def earliest_open_minutes(opening_hours: Iterable[dict] | None) -> int | None:
    """Return the earliest opening minute-of-day across all entries."""

    minutes = [
        start
        for start, _ in extract_time_intervals(opening_hours)
        if 0 <= start < 24 * 60
    ]
    return min(minutes) if minutes else None


def latest_close_minutes(opening_hours: Iterable[dict] | None) -> int | None:
    """Return the latest closing minute-of-day across all entries."""

    minutes: list[int] = []
    for _, end in extract_time_intervals(opening_hours):
        if 0 <= end <= 48 * 60:
            minutes.append(end if end <= 24 * 60 else end - 24 * 60)
    return max(minutes) if minutes else None
