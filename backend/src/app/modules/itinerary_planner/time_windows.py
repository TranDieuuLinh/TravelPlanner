from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.modules.itinerary_planner.contract import TimeInterval
from app.modules.itinerary_planner.policies import (
    ITINERARY_END_MINUTE,
    ITINERARY_START_MINUTE,
)


@dataclass(frozen=True, order=True, slots=True)
class PlanningWindow:
    start_minute: int
    end_minute: int

    @property
    def duration_minutes(self) -> int:
        return self.end_minute - self.start_minute


def normalize_interval(interval: TimeInterval) -> PlanningWindow | None:
    end = interval.end_minute
    if end <= interval.start_minute:
        end += 1440
    start = max(interval.start_minute, ITINERARY_START_MINUTE)
    end = min(end, ITINERARY_END_MINUTE)
    if end <= start:
        return None
    return PlanningWindow(start, end)


def normalize_and_merge(intervals: Iterable[TimeInterval]) -> tuple[PlanningWindow, ...]:
    windows = sorted(
        window
        for interval in intervals
        if (window := normalize_interval(interval)) is not None
    )
    if not windows:
        return ()

    merged: list[PlanningWindow] = [windows[0]]
    for window in windows[1:]:
        previous = merged[-1]
        if window.start_minute <= previous.end_minute:
            merged[-1] = PlanningWindow(
                previous.start_minute,
                max(previous.end_minute, window.end_minute),
            )
        else:
            merged.append(window)
    return tuple(merged)


def full_itinerary_window() -> tuple[PlanningWindow, ...]:
    return (PlanningWindow(ITINERARY_START_MINUTE, ITINERARY_END_MINUTE),)


def windows_fitting_duration(
    windows: Iterable[PlanningWindow],
    duration_minutes: int,
) -> tuple[PlanningWindow, ...]:
    return tuple(
        window for window in windows if window.duration_minutes >= duration_minutes
    )


def feasible_start_window(
    opening: PlanningWindow,
    earliest_start: int,
    latest_start: int,
    duration_minutes: int,
) -> PlanningWindow | None:
    start = max(opening.start_minute, earliest_start)
    latest = min(opening.end_minute - duration_minutes, latest_start)
    if latest < start:
        return None
    return PlanningWindow(start, latest)
