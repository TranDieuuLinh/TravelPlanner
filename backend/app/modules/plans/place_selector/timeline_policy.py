from __future__ import annotations

from dataclasses import dataclass

from app.modules.plans.place_selector.time_windows import format_clock_window


DAY_START_MINUTES = 8 * 60
DAY_END_MINUTES = 21 * 60
DEFAULT_ACTIVITY_DURATION_MINUTES = 90
DEFAULT_TRANSITION_MINUTES = 15
MINIMUM_FILLABLE_GAP_MINUTES = 45


@dataclass(frozen=True)
class MealAnchor:
    role: str
    start_minutes: int
    duration_minutes: int = 60

    @property
    def end_minutes(self) -> int:
        return self.start_minutes + self.duration_minutes

    @property
    def time_window(self) -> str:
        return format_clock_window(self.start_minutes, self.duration_minutes)


@dataclass(frozen=True)
class ActivityWindow:
    start_minutes: int
    end_minutes: int


MEAL_ANCHORS = (
    MealAnchor("breakfast_meal", 8 * 60),
    MealAnchor("lunch_meal", 12 * 60),
    MealAnchor("dinner_meal", 18 * 60),
)

ACTIVITY_WINDOWS = (
    ActivityWindow(9 * 60, 12 * 60),
    ActivityWindow(13 * 60, 18 * 60),
    ActivityWindow(19 * 60, DAY_END_MINUTES),
)

DAILY_ACTIVITY_MINUTES = sum(
    window.end_minutes - window.start_minutes for window in ACTIVITY_WINDOWS
)


def selected_activity_duration(source_duration_minutes: int | None) -> int:
    return source_duration_minutes or DEFAULT_ACTIVITY_DURATION_MINUTES


def activity_allocation_cost(source_duration_minutes: int | None) -> int:
    return (
        selected_activity_duration(source_duration_minutes) + DEFAULT_TRANSITION_MINUTES
    )
