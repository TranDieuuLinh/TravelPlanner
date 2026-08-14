from app.modules.itinerary_planner.tests.factories import candidate
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    base_payload,
    solve_payload,
)


def test_relationship_is_counted_once_and_repeated_tags_are_penalized() -> None:
    first = candidate("museum_a", priority="user_input", relationships=["museum_b"])
    second = candidate("museum_b", priority="user_input")
    first["tags"] = second["tags"] = ["museum", "culture"]

    result, _, _ = solve_payload(base_payload(places=[first, second]))

    assert result.objective_components["relationshipValue"] == 250
    assert result.objective_components["activityDiversityCost"] > 0
    assert "specialNearBonus" not in result.objective_components


def test_nine_hour_rest_delays_next_day_after_late_activity() -> None:
    nightlife = candidate(
        "late_show",
        priority="user_input",
        opening_hours={
            "1": [{"startMinute": 1439, "endMinute": 180}],
            "2": [],
        },
        duration_minutes=181,
    )
    nightlife["tags"] = ["nightlife", "live_music"]

    result, _, _ = solve_payload(base_payload(days=2, places=[nightlife]))

    late = next(stop for stop in result.scheduled_stops if stop.place_id == "late_show")
    first_day_two = min(
        stop.start_minute for stop in result.scheduled_stops if stop.day == 2
    )
    assert late.end_minute == 1620
    assert first_day_two + 1440 - late.end_minute >= 540


def test_bayesian_quality_prefers_reliable_reviews_over_sparse_five_star() -> None:
    reliable = candidate("reliable", priority="user_input")
    reliable.update({"rating": 4.8, "reviewCount": 2_000})
    sparse = candidate("sparse", priority="user_input")
    sparse.update({"rating": 5.0, "reviewCount": 1})

    reliable_result, _, _ = solve_payload(base_payload(places=[reliable]))
    sparse_result, _, _ = solve_payload(base_payload(places=[sparse]))

    assert (
        reliable_result.objective_components["placeQualityValue"]
        > sparse_result.objective_components["placeQualityValue"]
    )
