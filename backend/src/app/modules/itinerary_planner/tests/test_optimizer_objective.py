from app.modules.itinerary_planner.tests.factories import candidate
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    base_payload,
    solve_payload,
)
from app.modules.itinerary_planner.optimizer.config import SolverConfig


def test_default_solver_is_deterministic_and_time_bounded() -> None:
    config = SolverConfig()

    assert config.num_search_workers == 1
    assert config.priority_timeout_seconds == 2
    assert config.utility_timeout_seconds == 5
    assert config.utility_relative_gap_limit == 0.05


def test_utility_gap_does_not_claim_exact_optimality() -> None:
    result, _, _ = solve_payload(base_payload())

    assert result.passes[0].optimality_proven
    assert not result.passes[1].optimality_proven
    assert not result.optimality_proven


def test_relationship_is_counted_once_and_repeated_tags_are_penalized() -> None:
    first = candidate("museum_a", priority="user_input", relationships=["museum_b"])
    second = candidate("museum_b", priority="user_input")
    first["tags"] = second["tags"] = ["museum", "culture"]

    result, _, _ = solve_payload(base_payload(places=[first, second]))

    assert result.objective_components["relationshipValue"] == 250
    assert result.objective_components["activityDiversityCost"] > 0
    assert "specialNearBonus" not in result.objective_components
    assert result.passes[-1].objective_value == result.objective_value
    positive = {
        "specialExperienceValue",
        "preferenceValue",
        "placeQualityValue",
        "popularityValue",
        "timeFitValue",
        "relationshipValue",
    }
    component_total = sum(
        value if name in positive else -value
        for name, value in result.objective_components.items()
    )
    assert component_total == result.objective_value


def test_vietnamese_knowledge_graph_tags_drive_diversity_penalty() -> None:
    first = candidate("temple_a", priority="user_input")
    second = candidate("temple_b", priority="user_input")
    first["tags"] = second["tags"] = ["Tâm linh", "Văn hóa", "kiến trúc"]

    result, prepared, _ = solve_payload(base_payload(places=[first, second]))

    assert prepared.candidate_by_id["temple_a"].tags == [
        "tâm_linh",
        "văn_hóa",
        "kiến_trúc",
    ]
    assert result.objective_components["activityDiversityCost"] > 0


def test_preference_selects_matching_candidate_when_only_one_can_fit() -> None:
    preferred = candidate(
        "preferred",
        opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
    )
    alternative = candidate(
        "alternative",
        opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
    )
    preferred["tags"] = ["culture"]
    alternative["tags"] = ["shopping"]
    raw = base_payload(places=[preferred, alternative])
    raw["trip"]["preferences"] = ["culture"]
    for meal in raw["food"]:
        meal["tags"] = ["meal"]

    result, _, _ = solve_payload(raw)

    selected = {stop.place_id for stop in result.scheduled_stops}
    assert "preferred" in selected
    assert "alternative" not in selected
    assert result.objective_components["preferenceValue"] == 600


def test_nine_hour_rest_delays_next_day_after_late_activity() -> None:
    nightlife = candidate(
        "late_show",
        priority="user_input",
        opening_hours={
            "1": [{"startMinute": 1319, "endMinute": 60}],
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
    assert late.end_minute == 1500
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
