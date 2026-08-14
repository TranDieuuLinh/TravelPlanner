import pytest

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

    assert prepared.feasible_windows[("unknown", 1)] == (
        PlanningWindow(480, 1380),
    )
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

    assert prepared.feasible_windows[("night_bar", 1)] == (
        PlanningWindow(1320, 1620),
    )
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
    assert prepared.trip.preferences == ["culture", "local_experience"]
    assert prepared.related_by_place["source"] == frozenset({"target"})
    assert prepared.related_by_place["target"] == frozenset()
    assert any("missing" in warning for warning in prepared.warnings)


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


def test_food_with_unknown_cost_is_retained_and_warned() -> None:
    unknown_cost = food("unknown_cost")
    unknown_cost["price"]["cost"] = None
    parsed = ItineraryPlannerInput.model_validate(payload(foods=[unknown_cost]))

    prepared = prepare_planning_problem(parsed)

    assert [item.place_id for item in prepared.valid_food] == ["unknown_cost"]
    assert prepared.discarded_optional == ()
    assert any(
        "unknown_cost" in warning and "excluded from the budget total" in warning
        for warning in prepared.warnings
    )


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
