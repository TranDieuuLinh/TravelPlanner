from datetime import timedelta

from app.modules.itinerary_planner.candidate_semantics import normalize_tag
from app.modules.itinerary_planner.contract import PlannerCandidate, PlannerTrip
from app.modules.itinerary_planner.policies import LATE_NIGHT_TAGS
from app.modules.itinerary_planner.time_windows import PlanningWindow


NIGHT_ACTIVITY_EARLIEST_START_MINUTE = 18 * 60
WEEKEND_WEEKDAYS = frozenset({4, 5, 6})
NIGHT_ONLY_TAGS = LATE_NIGHT_TAGS | frozenset({"night_market", "night_marketplace"})


def apply_activity_time_policy(
    candidate: PlannerCandidate,
    trip: PlannerTrip,
    day: int,
    windows: tuple[PlanningWindow, ...],
) -> tuple[PlanningWindow, ...]:
    """Apply semantic night/weekend boundaries after direct opening hours."""
    if _is_weekend_only(candidate):
        date = trip.start_date + timedelta(days=day - 1)
        if date.weekday() not in WEEKEND_WEEKDAYS:
            return ()
    if not _is_night_only(candidate):
        return windows
    return tuple(
        PlanningWindow(
            max(window.start_minute, NIGHT_ACTIVITY_EARLIEST_START_MINUTE),
            window.end_minute,
        )
        for window in windows
        if window.end_minute > NIGHT_ACTIVITY_EARLIEST_START_MINUTE
    )


def _is_night_only(candidate: PlannerCandidate) -> bool:
    tags = set(candidate.tags)
    name = normalize_tag(candidate.name)
    return bool(tags & NIGHT_ONLY_TAGS) or "night_market" in name


def _is_weekend_only(candidate: PlannerCandidate) -> bool:
    tags = set(candidate.tags)
    name = normalize_tag(candidate.name)
    return "weekend_only" in tags or "weekend_night_market" in name
