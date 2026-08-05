from app.modules.plans.domain.entities import PlanDay, PlanItem, PlanTransportLeg
from app.modules.plans.dto.agent_contracts import (
    PlaceSelectionInput,
    PlanningIntent,
    SelectedPlaceContext,
    TripPlanningSpec,
)
from app.modules.plans.itinerary_optimizer import RouteFirstItineraryOptimizer
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.place_selector.service import PlaceSelectorService


def _item(
    item_id: str,
    name: str,
    window: str,
    *,
    duration: int,
    role: str,
    category: str = "activity",
) -> PlanItem:
    return PlanItem(
        itemId=item_id,
        name=name,
        timeWindow=window,
        placeType="restaurant" if category == "food" else "attraction",
        timelineCategory=category,
        durationMinutes=duration,
        role=role,
    )


def _leg(left: PlanItem, right: PlanItem, minutes: int) -> PlanTransportLeg:
    return PlanTransportLeg(
        fromItemId=left.item_id,
        toItemId=right.item_id,
        fromPlace=left.name,
        toPlace=right.name,
        mode="car",
        distanceMeters=1_000,
        estimatedDurationMinutes=minutes,
    )


def test_timeline_can_fit_more_than_two_activities_without_pace_quota() -> None:
    breakfast = _item(
        "breakfast",
        "Breakfast",
        "08:00-09:00",
        duration=60,
        role="breakfast_meal",
        category="food",
    )
    lunch = _item(
        "lunch",
        "Lunch",
        "12:00-13:00",
        duration=60,
        role="lunch_meal",
        category="food",
    )
    dinner = _item(
        "dinner",
        "Dinner",
        "18:00-19:00",
        duration=60,
        role="dinner_meal",
        category="food",
    )
    activities = [
        _item(
            f"activity-{index}",
            f"Activity {index}",
            f"{9 + index - 1:02d}:00-{9 + index:02d}:00",
            duration=45,
            role=f"main_activity_{index}",
        )
        for index in range(1, 4)
    ]
    ordered = [breakfast, *activities, lunch, dinner]
    legs = [_leg(left, right, 10) for left, right in zip(ordered, ordered[1:])]

    scheduled, overflow = PlaceSelectorService._apply_travel_aware_timeline(
        ordered, legs
    )

    assert overflow == []
    assert sum(item.timeline_category == "activity" for item in scheduled) == 3
    assert {
        item.role: item.time_window
        for item in scheduled
        if item.timeline_category == "food"
    } == {
        "breakfast_meal": "08:00-09:00",
        "lunch_meal": "12:00-13:00",
        "dinner_meal": "18:00-19:00",
    }
    assert [
        item.time_window for item in scheduled if item.timeline_category == "activity"
    ] == ["09:10-09:55", "10:05-10:50", "11:00-11:45"]


def test_timeline_overflows_activity_when_route_time_misses_next_meal() -> None:
    breakfast = _item(
        "breakfast",
        "Breakfast",
        "08:00-09:00",
        duration=60,
        role="breakfast_meal",
        category="food",
    )
    activity = _item(
        "activity",
        "Long visit",
        "09:00-11:30",
        duration=150,
        role="main_activity_1",
    )
    lunch = _item(
        "lunch",
        "Lunch",
        "12:00-13:00",
        duration=60,
        role="lunch_meal",
        category="food",
    )

    scheduled, overflow = PlaceSelectorService._apply_travel_aware_timeline(
        [breakfast, activity, lunch],
        [_leg(breakfast, activity, 20), _leg(activity, lunch, 20)],
    )

    assert [item.item_id for item in overflow] == ["activity"]
    assert [item.item_id for item in scheduled] == ["breakfast", "lunch"]


def test_route_first_selector_schedules_by_minutes_instead_of_activity_count() -> None:
    selector = PlaceSelectorService(
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer())
    )
    selection_input = PlaceSelectionInput(
        intent=PlanningIntent(destination="Hà Nội"),
        tripSpec=TripPlanningSpec(days=1),
        regionKey="vn,ha-noi",
        selectedPlaces=[
            SelectedPlaceContext(
                name=f"Stop {index}",
                sourceDurationMinutes=45,
                sourceOrder=index,
            )
            for index in range(1, 5)
        ],
        allowPlaceSuggestions=False,
    )

    result = selector.fill_agent_plan(selection_input)

    scheduled = [
        item
        for day in result.final_days
        for item in day.items
        if item.timeline_category == "activity"
    ]
    assert [item.name for item in scheduled] == ["Stop 1", "Stop 2", "Stop 3", "Stop 4"]
    assert result.unscheduled_places == []


def test_overflow_retries_once_in_another_day() -> None:
    meals = [
        _item(
            role,
            role.replace("_", " ").title(),
            window,
            duration=60,
            role=role,
            category="food",
        )
        for role, window in (
            ("breakfast_meal", "08:00-09:00"),
            ("lunch_meal", "12:00-13:00"),
            ("dinner_meal", "18:00-19:00"),
        )
    ]
    day_one = PlanDay(
        day=1,
        theme="Day 1",
        items=[
            meals[0],
            _item(
                "a1",
                "Long morning",
                "09:00-11:30",
                duration=150,
                role="main_activity_1",
            ),
            meals[1],
            _item(
                "a2",
                "Long afternoon",
                "13:00-17:30",
                duration=270,
                role="main_activity_2",
            ),
            meals[2],
            _item("a3", "Evening", "19:00-20:30", duration=90, role="main_activity_3"),
        ],
    )
    day_two = PlanDay(day=2, theme="Day 2", items=list(meals))
    overflow = _item(
        "overflow",
        "Overflow stop",
        "10:00-11:30",
        duration=90,
        role="main_activity_4",
    )
    selector = PlaceSelectorService(
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer())
    )

    days, remaining = selector._retry_overflow_on_other_day(
        [day_one, day_two],
        [overflow],
        trip_start_date=None,
        preferred_modes=set(),
        avoid_modes=set(),
    )

    assert remaining == []
    assert "Overflow stop" in [item.name for item in days[1].items]
