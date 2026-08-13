from app.modules.itinerary_planner.contract import TimeInterval
from app.modules.itinerary_planner.time_windows import (
    PlanningWindow,
    normalize_and_merge,
    normalize_interval,
)
from app.modules.itinerary_planner.policies import OVERNIGHT_END_MINUTE


def test_normalizes_overnight_window_to_next_day_0300_cap() -> None:
    interval = TimeInterval(startMinute=1320, endMinute=180)

    assert normalize_interval(interval, OVERNIGHT_END_MINUTE) == PlanningWindow(
        1320, 1620
    )


def test_clamps_window_to_itinerary_operating_range() -> None:
    interval = TimeInterval(startMinute=0, endMinute=1440)

    assert normalize_interval(interval) == PlanningWindow(480, 1380)


def test_merges_overlapping_and_touching_windows() -> None:
    intervals = [
        TimeInterval(startMinute=540, endMinute=600),
        TimeInterval(startMinute=590, endMinute=660),
        TimeInterval(startMinute=660, endMinute=720),
    ]

    assert normalize_and_merge(intervals) == (PlanningWindow(540, 720),)
