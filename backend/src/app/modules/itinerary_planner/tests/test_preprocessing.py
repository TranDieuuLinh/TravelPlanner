import pytest
from pydantic import ValidationError

from app.modules.itinerary_planner.contract import ItineraryPlannerInput, MealType
from app.modules.itinerary_planner.preprocessing import (
    PlanningPreflightError,
    prepare_planning_problem,
)
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.time_windows import PlanningWindow


def test_unknown_opening_is_full_planning_window_and_warned() -> None:
    parsed = ItineraryPlannerInput.model_validate(
        payload(places=[candidate("unknown", priority="user_input")])
    )

    prepared = prepare_planning_problem(parsed)

    assert prepared.feasible_windows[("unknown", 1)] == (PlanningWindow(480, 1380),)
    assert prepared.unknown_opening_days["unknown"] == frozenset({1})
    assert any("unknown" in warning for warning in prepared.warnings)


def test_only_late_night_place_can_use_overnight_window() -> None:
    nightlife = candidate(
        "night_bar",
        opening_hours={"1": [{"startMinute": 1320, "endMinute": 180}]},
        duration_minutes=180,
    )
    nightlife["tags"] = ["bar", "drinking"]
    parsed = ItineraryPlannerInput.model_validate(payload(places=[nightlife]))

    prepared = prepare_planning_problem(parsed)

    assert prepared.feasible_windows[("night_bar", 1)] == (PlanningWindow(1320, 1620),)
    assert prepared.late_night_eligible_ids == frozenset({"night_bar"})


def test_regular_place_is_clamped_at_2300() -> None:
    regular = candidate(
        "late_museum",
        opening_hours={"1": [{"startMinute": 1320, "endMinute": 180}]},
        duration_minutes=60,
    )
    regular["tags"] = ["museum", "culture"]
    parsed = ItineraryPlannerInput.model_validate(payload(places=[regular]))

    prepared = prepare_planning_problem(parsed)

    assert prepared.feasible_windows[("late_museum", 1)] == (
        PlanningWindow(1320, 1380),
    )
    assert not prepared.late_night_eligible_ids


def test_empty_opening_list_is_closed_not_unknown() -> None:
    parsed = ItineraryPlannerInput.model_validate(
        payload(
            places=[
                candidate(
                    "closed",
                    priority="user_input",
                    opening_hours={"1": []},
                )
            ]
        )
    )

    prepared = prepare_planning_problem(parsed)

    assert "closed" not in prepared.candidate_by_id
    assert prepared.unscheduled_priority[0].reason_code == "closed_for_entire_trip"
    assert "closed" not in prepared.unknown_opening_ids


def test_duration_must_fit_a_single_opening_window() -> None:
    parsed = ItineraryPlannerInput.model_validate(
        payload(
            places=[
                candidate(
                    "too_long",
                    duration_minutes=90,
                    opening_hours={
                        "1": [
                            {"startMinute": 540, "endMinute": 600},
                            {"startMinute": 660, "endMinute": 720},
                        ]
                    },
                )
            ]
        )
    )

    prepared = prepare_planning_problem(parsed)

    assert prepared.discarded_optional[0].reason_code == (
        "duration_exceeds_every_opening_window"
    )


def test_normalizes_tags_and_keeps_relationship_one_way() -> None:
    source = candidate(
        "source",
        relationships=["target", "missing", "target"],
    )
    parsed = ItineraryPlannerInput.model_validate(
        payload(places=[source, candidate("target")])
    )

    prepared = prepare_planning_problem(parsed)

    assert prepared.candidate_by_id["source"].tags == [
        "local_experience",
        "culture",
    ]
    assert prepared.trip.preferences.tags == ["culture", "local_experience"]
    assert prepared.related_by_place["source"] == frozenset({"target"})
    assert prepared.related_by_place["target"] == frozenset()
    assert any("missing" in warning for warning in prepared.warnings)


def test_excludes_adult_only_and_avoided_candidates_for_trip_with_kids() -> None:
    adult = candidate(
        "adult_bar",
        priority="user_input",
        audience={"adultOnly": True, "kidSuitable": False},
    )
    avoided = candidate("night_market", priority="user_input")
    avoided["tags"] = ["nightlife"]
    raw = payload(places=[adult, avoided])
    raw["trip"]["people"] = 3
    raw["trip"]["party"] = {"adults": 2, "kids": 1}
    raw["trip"]["preferences"]["avoidTags"] = ["nightlife"]

    prepared = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))

    reasons = {
        item.place_id: item.reason_code for item in prepared.unscheduled_priority
    }
    assert reasons == {
        "adult_bar": "adult_only",
        "night_market": "avoided_tag",
    }


def test_unknown_audience_is_not_assumed_unsafe_for_kids() -> None:
    raw = payload(places=[candidate("unknown_audience")])
    raw["trip"]["people"] = 3
    raw["trip"]["party"] = {"adults": 2, "kids": 1}

    prepared = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))

    assert "unknown_audience" in prepared.candidate_by_id


def test_meal_eligibility_uses_meal_start_and_duration() -> None:
    lunch = food(
        "lunch_only",
        supported_meals=["lunch"],
        opening_hours={"1": [{"startMinute": 720, "endMinute": 780}]},
    )
    all_meals = food("coverage")
    parsed = ItineraryPlannerInput.model_validate(payload(foods=[lunch, all_meals]))

    prepared = prepare_planning_problem(parsed)

    assert prepared.meal_eligibility[("lunch_only", 1, MealType.lunch)] == (
        PlanningWindow(720, 720),
    )


def test_food_with_unknown_cost_is_rejected_at_input_boundary() -> None:
    unknown_cost = food("unknown_cost")
    unknown_cost["price"]["cost"] = None

    with pytest.raises(ValidationError) as error:
        ItineraryPlannerInput.model_validate(payload(foods=[unknown_cost]))

    assert error.value.errors()[0]["loc"] == ("food", 0, "price", "cost")


def test_preflight_reports_each_missing_day_and_meal() -> None:
    parsed = ItineraryPlannerInput.model_validate(
        payload(days=2, foods=[food(supported_meals=["lunch", "dinner"])])
    )

    with pytest.raises(PlanningPreflightError) as error:
        prepare_planning_problem(parsed)

    assert [(item.day, item.meal) for item in error.value.missing_meals] == [
        (1, MealType.breakfast),
        (2, MealType.breakfast),
    ]


def test_geographic_projection_keeps_priority_global_and_links_special_near() -> None:
    places = [candidate(f"optional_{index}") for index in range(4)]
    places.append(candidate("required", priority="user_input"))
    for index, place in enumerate(places):
        place["coordinates"] = {
            "latitude": 21.0 + index / 100,
            "longitude": 105.8,
        }
    linked = food("linked")
    linked["relationships"] = ["optional_0"]
    coverage = [food(f"coverage_{index}") for index in range(3)]
    for item in coverage:
        item["priority"] = "user_input"

    prepared = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(days=4, places=places, foods=[linked, *coverage])
        )
    )

    assert 1 <= len(prepared.feasible_days["optional_0"]) <= 2
    assert prepared.feasible_days["required"] == frozenset({1, 2, 3, 4})
    assert prepared.feasible_days["linked"] == prepared.feasible_days["optional_0"]
    assert any("Geographic day-domain projection" in item for item in prepared.warnings)


def test_geographic_projection_balances_small_daily_pool() -> None:
    places = [candidate(f"place_{index}") for index in range(4)]
    foods = [food(f"meal_food_{index}") for index in range(3)]

    prepared = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(days=4, places=places, foods=foods)
        )
    )

    assert [
        sum(
            day in prepared.feasible_days[item.place_id]
            for item in prepared.valid_places
        )
        for day in range(1, 5)
    ] == [2, 2, 2, 2]
    assert prepared.canonical_place_id_by_candidate_id == {}


def test_outlier_cannot_deplete_a_daily_activity_reserve() -> None:
    places = [candidate(f"city_{index:02d}") for index in range(41)]
    for index, item in enumerate(places):
        item["coordinates"] = {
            "latitude": 21.02 + index / 100_000,
            "longitude": 105.84 + index / 100_000,
        }
    outlier = candidate("zz_ba_vi")
    outlier["coordinates"] = {"latitude": 21.13, "longitude": 105.38}
    foods = [food(f"restaurant_{index:02d}") for index in range(18)]

    prepared = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(days=3, places=[*places, outlier], foods=foods)
        )
    )

    daily_counts = [
        sum(
            day in prepared.feasible_days[item.place_id]
            for item in prepared.valid_places
        )
        for day in range(1, 4)
    ]
    assert daily_counts == [14, 14, 14]


def test_repeats_restaurant_only_when_original_pool_has_no_distinct_matching() -> None:
    prepared = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(
                places=[candidate("activity_1"), candidate("activity_2")],
                foods=[food("one_restaurant")],
            )
        )
    )

    aliases = prepared.canonical_place_id_by_candidate_id
    assert len(aliases) == 3
    assert set(aliases.values()) == {"one_restaurant"}
    assert {
        meal
        for alias_id in aliases
        for candidate_id, day, meal in prepared.meal_eligibility
        if candidate_id == alias_id and day == 1
    } == set(MealType)
    assert any("Repeated restaurant fallback" in item for item in prepared.warnings)
