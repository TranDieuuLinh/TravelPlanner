from __future__ import annotations

from datetime import datetime, timezone

from app.modules.plans.domain.entities import PlanDay, PlanItem
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.provider import TravelTimeMatrix


class CoordinateMatrixProvider:
    def calculate(
        self,
        coordinates,
        *,
        transport_mode,
        departure_time,
    ):
        return TravelTimeMatrix(
            travel_times_seconds=[
                [
                    int(abs(origin[1] - destination[1]) * 100)
                    for destination in coordinates
                ]
                for origin in coordinates
            ],
            provider="test_matrix",
            fetched_at=datetime.now(timezone.utc),
        )


class FailingMatrixProvider:
    def calculate(self, coordinates, *, transport_mode, departure_time):
        raise RuntimeError("matrix unavailable")


def test_trip_optimizer_groups_nearby_activities_across_days() -> None:
    optimizer = _optimizer(CoordinateMatrixProvider())
    days = [
        _day(1, [_activity("a", 0, "08:00-09:00"), _activity("b", 100, "10:00-11:00")]),
        _day(2, [_activity("c", 1, "08:00-09:00"), _activity("d", 101, "10:00-11:00")]),
    ]

    optimized = optimizer.optimize_trip(days)

    memberships = [
        {item.place_id for item in day.items}
        for day in optimized
    ]
    assert {"a", "c"} in memberships
    assert {"b", "d"} in memberships
    assert [item.time_window for item in optimized[0].items] == [
        "08:00-09:00",
        "10:00-11:00",
    ]


def test_day_optimizer_keeps_meal_anchor_but_reorders_activities() -> None:
    optimizer = _optimizer(CoordinateMatrixProvider())
    items = [
        _activity("far", 10, "08:00-09:00", role="main_activity"),
        _meal("meal", 2, "12:00-13:00"),
        _activity("near", 1, "14:00-15:00", role="support_activity"),
    ]

    optimized, _ = optimizer.optimize(items, start=(0.0, 0.0))

    assert [item.place_id for item in optimized] == ["near", "meal", "far"]
    assert optimized[0].role == "main_activity"
    assert optimized[0].time_window == "08:00-09:00"
    assert optimized[1].role == "lunch_meal"
    assert optimized[1].time_window == "12:00-13:00"
    assert optimized[2].role == "support_activity"
    assert optimized[2].time_window == "14:00-15:00"


def test_day_optimizer_penalizes_missing_graph_preferred_window() -> None:
    optimizer = _optimizer(CoordinateMatrixProvider())
    timed = _activity("far", 10, "08:00-09:00", role="main_activity").model_copy(
        update={
            "preferred_time_windows": [
                {"start": "08:00", "end": "09:00"}
            ]
        }
    )
    items = [
        timed,
        _meal("meal", 2, "12:00-13:00"),
        _activity("near", 1, "14:00-15:00", role="support_activity"),
    ]

    optimized, _ = optimizer.optimize(items, start=(0.0, 0.0))

    assert [item.place_id for item in optimized] == ["far", "meal", "near"]
    assert optimized[0].time_window == "08:00-09:00"


def test_source_day_activity_never_moves_to_another_day() -> None:
    optimizer = _optimizer(CoordinateMatrixProvider())
    fixed = _activity("url-stop", 100, "08:00-09:00").model_copy(
        update={"source_day": 1, "source_order": 1}
    )
    days = [
        _day(1, [fixed, _activity("a", 0, "10:00-11:00")]),
        _day(2, [_activity("b", 101, "08:00-09:00"), _activity("c", 1, "10:00-11:00")]),
    ]

    optimized = optimizer.optimize_trip(days)

    assert optimized[0].items[0].place_id == "url-stop"
    assert optimized[0].items[0].source_day == 1


def test_url_provenance_without_day_or_order_can_move_between_days() -> None:
    optimizer = _optimizer(CoordinateMatrixProvider())
    url_stop = _activity("url-stop", 100, "08:00-09:00").model_copy(
        update={"source_refs": ["https://example.com/reel"]}
    )
    days = [
        _day(1, [_activity("a", 0, "08:00-09:00"), url_stop]),
        _day(2, [_activity("b", 101, "08:00-09:00"), _activity("c", 1, "10:00-11:00")]),
    ]

    optimized = optimizer.optimize_trip(days)

    memberships = [{item.place_id for item in day.items} for day in optimized]
    assert {"url-stop", "b"} in memberships
    assert {"a", "c"} in memberships


def test_matrix_failure_preserves_existing_day_order() -> None:
    optimizer = _optimizer(FailingMatrixProvider())
    items = [
        _activity("far", 10, "08:00-09:00"),
        _activity("near", 1, "10:00-11:00"),
    ]

    optimized, _ = optimizer.optimize(items, start=(0.0, 0.0))

    assert [item.place_id for item in optimized] == ["far", "near"]


def _optimizer(matrix_provider) -> RouteFirstItineraryOptimizer:
    legacy = GeographicRouteOptimizer(matrix_provider=matrix_provider)
    return RouteFirstItineraryOptimizer(legacy, matrix_provider)


def _day(day: int, items: list[PlanItem]) -> PlanDay:
    return PlanDay(
        day=day,
        theme="Flexible city exploration",
        strategy="route_first",
        items=items,
    )


def _activity(
    place_id: str,
    longitude: float,
    time_window: str,
    *,
    role: str = "activity",
) -> PlanItem:
    return PlanItem(
        itemId=f"item-{place_id}",
        placeId=place_id,
        name=place_id,
        timeWindow=time_window,
        placeType="attraction",
        timelineCategory="activity",
        role=role,
        source="finder_suggestion",
        durationMinutes=60,
        latitude=0.0,
        longitude=longitude,
    )


def _meal(place_id: str, longitude: float, time_window: str) -> PlanItem:
    return PlanItem(
        itemId=f"item-{place_id}",
        placeId=place_id,
        name=place_id,
        timeWindow=time_window,
        placeType="restaurant",
        timelineCategory="food",
        role="lunch_meal",
        source="finder_suggestion",
        durationMinutes=60,
        latitude=0.0,
        longitude=longitude,
    )
