from __future__ import annotations

from typing import Any

from app.modules.plans.domain.entities import PreferredTimeWindow
from app.modules.plans.place_selector.time_windows import (
    time_window_matches_preference,
)


def _markers(value: Any) -> set[str]:
    return {
        str(getattr(value, "place_type", "") or "")
        .strip()
        .casefold()
        .replace(" ", "_"),
        *(
            str(tag).strip().casefold().replace(" ", "_")
            for tag in (getattr(value, "tags", []) or [])
        ),
        str(getattr(value, "activity_id", "") or "").strip().casefold(),
    }


def is_time_sensitive_visit(value: Any) -> bool:
    return bool(
        _markers(value).intersection(
            {"fresh_market", "morning_market", "night_market"}
        )
    )


def effective_preferred_time_windows(value: Any) -> list[PreferredTimeWindow]:
    existing = list(getattr(value, "preferred_time_windows", []) or [])
    if existing:
        return existing
    markers = _markers(value)
    if markers.intersection({"fresh_market", "morning_market"}):
        return [PreferredTimeWindow(start="05:00", end="08:00")]
    if "night_market" in markers:
        return [PreferredTimeWindow(start="18:00", end="23:00")]
    return []


def matches_effective_preference(
    value: Any,
    time_window: str,
    duration_minutes: int,
) -> bool:
    windows = effective_preferred_time_windows(value)
    return not windows or time_window_matches_preference(
        time_window,
        duration_minutes,
        windows,
    )
