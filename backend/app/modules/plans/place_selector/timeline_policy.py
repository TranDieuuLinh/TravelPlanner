from __future__ import annotations

from dataclasses import dataclass

from app.modules.plans.place_selector.time_windows import format_clock_window


DAY_START_MINUTES = 8 * 60
DAY_END_MINUTES = 21 * 60
DEFAULT_ACTIVITY_DURATION_MINUTES = 90
DEFAULT_TRANSITION_MINUTES = 15
MINIMUM_FILLABLE_GAP_MINUTES = 45
MAX_MAIN_FOOD_RATIO = 0.4


@dataclass(frozen=True)
class MealAnchor:
    role: str
    start_minutes: int
    duration_minutes: int = 60
    earliest_start_minutes: int | None = None
    latest_start_minutes: int | None = None

    @property
    def earliest(self) -> int:
        return self.earliest_start_minutes or self.start_minutes

    @property
    def latest(self) -> int:
        return self.latest_start_minutes or self.start_minutes

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
    # The target is used for ranking and the window is a soft constraint. A
    # late attraction must be able to push lunch/dinner without creating a
    # fake overlap.
    MealAnchor("breakfast_meal", 8 * 60, earliest_start_minutes=7 * 60, latest_start_minutes=9 * 60 + 30),
    MealAnchor("lunch_meal", 12 * 60, earliest_start_minutes=11 * 60 + 30, latest_start_minutes=14 * 60),
    MealAnchor("dinner_meal", 18 * 60, earliest_start_minutes=17 * 60 + 30, latest_start_minutes=20 * 60),
)

ACTIVITY_WINDOWS = (
    ActivityWindow(9 * 60, 12 * 60),
    ActivityWindow(13 * 60, 18 * 60),
    ActivityWindow(19 * 60, DAY_END_MINUTES),
)

DAILY_ACTIVITY_MINUTES = sum(
    window.end_minutes - window.start_minutes for window in ACTIVITY_WINDOWS
)


def time_hint_period(hint: str | None) -> str | None:
    """Normalize URL/KG timing hints to the three planner day parts."""
    value = (hint or "").casefold().replace("-", " ").replace("_", " ")
    if any(token in value for token in ("night", "evening", "after dark", "sunset", "dinner")):
        return "evening"
    if any(token in value for token in ("afternoon", "lunch", "noon")):
        return "afternoon"
    if any(token in value for token in ("morning", "breakfast", "sunrise")):
        return "morning"
    return None


def activity_window_period(index: int) -> str:
    return ("morning", "afternoon", "evening")[min(index, 2)]


def hint_matches_activity_window(hint: str | None, index: int) -> bool:
    period = time_hint_period(hint)
    return period is None or period == activity_window_period(index)


def selected_activity_duration(source_duration_minutes: int | None) -> int:
    return source_duration_minutes or DEFAULT_ACTIVITY_DURATION_MINUTES


def resolve_timing_precedence(
    edge_time_slots: list | None,
    node_best_time_slots: list | None,
    generic_window: str | None,
) -> list | str | None:
    """Apply graph timing precedence without inventing a new output field."""
    return edge_time_slots or node_best_time_slots or generic_window


def resolve_duration_precedence(
    edge_recommended_visit_minutes: int | None,
    node_typical_duration_minutes: int | None,
    default_minutes: int = DEFAULT_ACTIVITY_DURATION_MINUTES,
) -> int:
    """Apply edge, node, then selector-default duration precedence."""
    return (
        edge_recommended_visit_minutes
        or node_typical_duration_minutes
        or default_minutes
    )


def activity_allocation_cost(source_duration_minutes: int | None) -> int:
    return (
        selected_activity_duration(source_duration_minutes) + DEFAULT_TRANSITION_MINUTES
    )
