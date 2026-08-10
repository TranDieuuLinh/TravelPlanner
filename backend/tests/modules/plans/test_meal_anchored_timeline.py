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
from app.modules.plans.place_selector.place_tool import SelectablePlace


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

    assert overflow == []
    assert [item.item_id for item in scheduled] == ["breakfast", "activity", "lunch"]
    assert (
        next(item for item in scheduled if item.role == "lunch_meal").time_window
        == "12:10-13:10"
    )


def test_shifted_meal_refits_following_activity_and_uses_default_transition() -> None:
    breakfast = _item(
        "breakfast",
        "Breakfast",
        "08:00-09:00",
        duration=60,
        role="breakfast_meal",
        category="food",
    )
    morning = _item(
        "morning",
        "Long morning",
        "09:00-11:30",
        duration=170,
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
    afternoon = _item(
        "afternoon",
        "Afternoon",
        "13:00-14:00",
        duration=60,
        role="main_activity_2",
    )

    scheduled, overflow = PlaceSelectorService._apply_travel_aware_timeline(
        [breakfast, morning, lunch, afternoon],
        [
            _leg(breakfast, morning, 20),
            _leg(morning, lunch, 30),
        ],
    )

    assert overflow == []
    assert {
        item.name: item.time_window
        for item in scheduled
    } == {
        "Breakfast": "08:00-09:00",
        "Long morning": "09:20-12:10",
        "Lunch": "12:40-13:40",
        "Afternoon": "13:55-14:55",
    }


def test_url_selected_stop_displaces_optional_finder_stop_after_route_fit() -> None:
    breakfast = _item(
        "breakfast",
        "Breakfast",
        "08:00-09:00",
        duration=60,
        role="breakfast_meal",
        category="food",
    )
    optional = _item(
        "optional",
        "Optional Finder stop",
        "09:00-19:00",
        duration=600,
        role="main_activity_1",
    ).model_copy(update={"source": "finder_suggestion"})
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
    url_stop = _item(
        "url-stop",
        "The Note Coffee",
        "19:00-22:00",
        duration=180,
        role="supporting_stop",
        category="food",
    ).model_copy(
        update={
            "source": "selected_place",
            "source_refs": ["https://example.com/hanoi"],
        }
    )

    scheduled, overflow = PlaceSelectorService()._apply_source_priority_timeline(
        [breakfast, optional, lunch, dinner, url_stop],
        [],
    )

    assert "The Note Coffee" in [item.name for item in scheduled]
    assert "Optional Finder stop" not in [item.name for item in scheduled]
    assert [item.name for item in overflow] == ["Optional Finder stop"]


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
        allowFinderGapFill=False,
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


def test_elapsed_url_time_hint_does_not_leave_selected_stop_unscheduled() -> None:
    selector = PlaceSelectorService(
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer())
    )
    selection_input = PlaceSelectionInput(
        intent=PlanningIntent(destination="Hà Nội"),
        tripSpec=TripPlanningSpec(days=1),
        regionKey="vn,ha-noi",
        selectedPlaces=[
            SelectedPlaceContext(
                name=name,
                ontologyType=(
                    "DrinkDessert" if name == "The Note Coffee" else None
                ),
                sourceRefs=["https://example.com/hanoi"],
                sourceDurationMinutes=120,
                sourceOrder=index,
                sourceTimeHint="morning",
            )
            for index, name in enumerate(
                ("Morning source stop", "The Note Coffee"),
                start=1,
            )
        ],
        allowFinderGapFill=False,
    )

    result = selector.fill_agent_plan(selection_input)

    scheduled_names = [
        item.name
        for day in result.final_days
        for item in day.items
    ]
    assert "Morning source stop" in scheduled_names
    assert "The Note Coffee" in scheduled_names
    assert result.unscheduled_places == []
    assert any(
        "source-suggested morning" in warning
        for warning in result.warnings
    )


class _RequiredTimingPlaceTool:
    def get(self, place_id: str) -> SelectablePlace | None:
        if place_id != "place-night-market":
            return None
        return SelectablePlace(
            placeId=place_id,
            name="Chợ đêm",
            placeType="attraction",
            regionKey="vn,ha-noi",
            latitude=21.03,
            longitude=105.85,
        )

    def search(self, **kwargs):
        return []


def _required_timing_input(duration: int) -> PlaceSelectionInput:
    return PlaceSelectionInput.model_validate(
        {
            "intent": {"destination": "Hà Nội"},
            "tripSpec": {"days": 1},
            "regionKey": "vn,ha-noi",
            "requiredExperiences": [
                {
                    "requirementId": "req-night-market",
                    "theme": "Chợ đêm",
                    "selectionPolicy": "required_anchor",
                    "anchorPlaceIds": ["place-night-market"],
                    "minimumRequired": 1,
                    "priority": "must",
                    "reason": "Trải nghiệm phù hợp vào buổi tối.",
                    "evidenceClaimIds": ["claim-night-market"],
                    "sourceRefs": ["https://example.com/night-market"],
                    "preferredTimeWindows": [{"start": "19:00", "end": "21:00"}],
                    "recommendedVisitMinutes": duration,
                }
            ],
            "allowFinderGapFill": False,
        }
    )


def test_route_first_uses_graph_preferred_time_window() -> None:
    selector = PlaceSelectorService(
        _RequiredTimingPlaceTool(),
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )

    result = selector.fill_agent_plan(_required_timing_input(60))

    activity = next(
        item
        for item in result.final_days[0].items
        if item.timeline_category == "activity"
    )
    assert activity.time_window == "19:15-20:15"
    assert activity.preferred_time_windows[0].start == "19:00"
    assert not any(
        "outside its graph-recommended" in warning for warning in result.warnings
    )


def test_route_first_falls_back_when_graph_window_cannot_fit_duration() -> None:
    selector = PlaceSelectorService(
        _RequiredTimingPlaceTool(),
        route_optimizer=RouteFirstItineraryOptimizer(GeographicRouteOptimizer()),
    )

    result = selector.fill_agent_plan(_required_timing_input(150))

    activity = next(
        item
        for item in result.final_days[0].items
        if item.timeline_category == "activity"
    )
    assert activity.time_window == "09:15-11:45"
    assert any(
        "outside its graph-recommended" in warning for warning in result.warnings
    )


def test_selected_meal_uses_catalog_window_when_source_hint_is_missing() -> None:
    place = SelectedPlaceContext.model_validate(
        {
            "placeId": "craft-beer",
            "name": "Local Craft Beer Restaurant",
            "ontologyType": "Restaurant",
            "preferredTimeWindows": [{"start": "18:00", "end": "21:00"}],
        }
    )

    assignments = PlaceSelectorService._selected_meal_role_refs([place])

    assert assignments == {"dinner_meal": "craft-beer"}


def test_second_evening_only_meal_is_not_moved_to_morning() -> None:
    places = [
        SelectedPlaceContext.model_validate(
            {
                "placeId": place_id,
                "name": name,
                "ontologyType": "Restaurant",
                "preferredTimeWindows": [{"start": "18:00", "end": "21:00"}],
            }
        )
        for place_id, name in (
            ("craft-beer", "Local Craft Beer Restaurant"),
            ("wine-bar", "Local Wine Bar"),
        )
    ]

    assignments = PlaceSelectorService._selected_meal_role_refs(places)

    assert assignments == {"dinner_meal": "craft-beer"}


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
