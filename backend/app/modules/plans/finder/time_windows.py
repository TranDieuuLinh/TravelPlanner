from __future__ import annotations

import re


_CLOCK_PATTERN = re.compile(r"(?<!\d)(\d{1,3}):([0-5]\d)")
_BOUNDED_CLOCK_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)")


def parse_clock_minutes(value: str) -> int | None:
    match = _BOUNDED_CLOCK_PATTERN.search(value)
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def parse_unbounded_clock_minutes(value: str) -> int | None:
    match = _CLOCK_PATTERN.search(value)
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def format_clock(minutes: int, *, bound_to_day: bool = False) -> str:
    if bound_to_day:
        minutes = min(minutes, 23 * 60 + 59)
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def format_clock_window(
    start: int,
    duration: int,
    *,
    bound_to_day: bool = False,
) -> str:
    return f"{format_clock(start, bound_to_day=bound_to_day)}-{format_clock(start + duration, bound_to_day=bound_to_day)}"


def window_duration(value: str) -> int | None:
    parts = value.split("-", 1)
    if len(parts) != 2:
        return None
    start = parse_unbounded_clock_minutes(parts[0])
    end = parse_unbounded_clock_minutes(parts[1])
    if start is None or end is None:
        return None
    return max(0, end - start)
