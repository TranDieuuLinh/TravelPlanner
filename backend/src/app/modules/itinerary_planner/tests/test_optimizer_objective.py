from dataclasses import replace

from app.modules.itinerary_planner.optimizer.config import SolverConfig
from app.modules.itinerary_planner.tests.factories import candidate, payload
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    base_payload,
    meal_candidates,
    solve_payload,
)


def test_default_solver_is_deterministic_without_wall_clock_deadlines() -> None:
    config = SolverConfig()

    assert config.num_search_workers == 1
    assert config.priority_timeout_seconds is None
    assert config.utility_timeout_seconds is None
    assert config.utility_relative_gap_limit == 0.05
    assert config.utility_parallel_workers == 3
    assert config.max_utility_no_improvement_rounds == 10


def test_utility_gap_does_not_claim_exact_optimality() -> None:
    result, _, _ = solve_payload(base_payload())

    assert result.passes[0].optimality_proven
    assert not result.passes[1].optimality_proven
    assert not result.optimality_proven
    assert result.passes[1].attempt_count == 1
    assert result.passes[1].no_improvement_rounds == 0


def test_utility_restart_keeps_the_highest_scoring_incumbent() -> None:
    config = replace(
        SolverConfig(),
        utility_timeout_seconds=1,
        utility_parallel_workers=3,
        max_utility_no_improvement_rounds=1,
        log_search_progress=False,
    )
    result, _, _ = solve_payload(base_payload(), config=config)

    utility = result.passes[-1]
    assert utility.objective_value == result.objective_value
    assert utility.attempt_count == utility.round_count * 3
    assert utility.attempt_count >= 3
    assert utility.no_improvement_rounds == 1


def test_relationship_is_counted_once_and_repeated_tags_are_penalized() -> None:
    first = candidate("museum_a", priority="user_input", relationships=["museum_b"])
    second = candidate("museum_b", priority="user_input")
    first["tags"] = second["tags"] = ["museum", "culture"]

    alternative = candidate("market_alternative")
    alternative["tags"] = ["shopping"]
    result, _, _ = solve_payload(base_payload(places=[first, second, alternative]))

    assert result.objective_components["relationshipValue"] == 250
    assert result.objective_components["sameDayTagRepetitionCost"] > 0
    assert "specialNearBonus" not in result.objective_components
    assert result.passes[-1].objective_value == result.objective_value
    positive = {
        "activityCoverageValue",
        "specialExperienceValue",
        "preferenceValue",
        "styleValue",
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

    alternative = candidate("museum_alternative")
    alternative["tags"] = ["bảo tàng"]
    result, prepared, _ = solve_payload(
        base_payload(places=[first, second, alternative])
    )

    assert prepared.candidate_by_id["temple_a"].tags == [
        "tâm_linh",
        "văn_hóa",
        "kiến_trúc",
    ]
    assert result.objective_components["sameDayTagRepetitionCost"] > 0


def test_broad_tags_and_exhausted_groups_do_not_force_repetition_cost() -> None:
    first = candidate("local_a", priority="user_input")
    second = candidate("local_b", priority="user_input")
    first["tags"] = second["tags"] = ["Văn hóa", "địa phương", "outdoor"]

    result, _, _ = solve_payload(base_payload(places=[first, second]))

    assert result.objective_components["sameDayTagRepetitionCost"] == 0


def test_activity_can_fill_gap_by_shifting_lunch_inside_meal_window() -> None:
    activity = candidate(
        "gap_activity",
        duration_minutes=90,
        opening_hours={"1": [{"startMinute": 615, "endMinute": 735}]},
    )
    activity["tags"] = ["museum"]
    afternoon = candidate(
        "afternoon_activity",
        priority="user_input",
        duration_minutes=120,
        opening_hours={"1": [{"startMinute": 840, "endMinute": 1020}]},
    )
    afternoon["tags"] = ["shopping"]

    result, _, _ = solve_payload(
        payload(places=[activity, afternoon], foods=meal_candidates())
    )

    stops = {stop.place_id: stop for stop in result.scheduled_stops}
    assert "gap_activity" in stops
    assert stops["lunch_1"].start_minute > 705


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


def test_style_selects_matching_candidate_only_when_user_requests_it() -> None:
    preferred = candidate(
        "slow_place",
        styles=["slow_travel"],
        opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
    )
    alternative = candidate(
        "fast_place",
        styles=["adventure"],
        opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
    )
    raw = base_payload(places=[preferred, alternative])
    raw["trip"]["preferences"] = {
        "tags": [],
        "avoidTags": [],
        "styles": ["slow_travel"],
    }
    for meal in raw["food"]:
        meal["tags"] = ["meal"]

    result, _, _ = solve_payload(raw)

    assert "slow_place" in {stop.place_id for stop in result.scheduled_stops}
    assert result.objective_components["styleValue"] == 400


def test_consecutive_places_with_overlapping_tags_are_penalized() -> None:
    first = candidate(
        "temple_a",
        priority="user_input",
        duration_minutes=30,
        relationships=["temple_b"],
        opening_hours={"1": [{"startMinute": 540, "endMinute": 570}]},
    )
    second = candidate(
        "temple_b",
        priority="user_input",
        duration_minutes=30,
        relationships=["temple_a"],
        opening_hours={"1": [{"startMinute": 570, "endMinute": 600}]},
    )
    first["tags"] = second["tags"] = ["temple", "history", "indoor"]

    result, _, _ = solve_payload(base_payload(places=[first, second]))

    assert result.objective_components["consecutiveTagRepetitionCost"] > 0


def test_seven_hour_rest_allows_flexible_next_day_start_after_late_activity() -> None:
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
    assert first_day_two + 1440 - late.end_minute >= 420


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
