from app.modules.itinerary_planner.beam_search.constraints import (
    fit_transition_window,
    is_restaurant,
    is_restaurant_to_restaurant,
    long_transition_allowed,
)
from app.modules.itinerary_planner.beam_search.config import BeamSearchConfig
from app.modules.itinerary_planner.beam_search.evaluation import evaluate_plan
from app.modules.itinerary_planner.beam_search.optimizer import (
    _DayState,
    category_sort_key,
    optimize_beam_search,
)
from app.modules.itinerary_planner.beam_search.pruning import (
    prune_day_states,
    repetition_sort_key,
)
from app.modules.itinerary_planner.beam_search.scoring import candidate_score
from app.modules.itinerary_planner.beam_search.constraints import is_travelplace
from app.modules.itinerary_planner.optimizer.result import ScheduledStop
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
import asyncio

from app.modules.itinerary_planner.adapters.transport_cost import (
    XanhSmTransportCostEstimator,
)
from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing import build_routing_problem
from app.modules.itinerary_planner.tests.routing_fakes import GeneratedMatrixProvider


def prepare_and_route(raw, matrix_provider=None):
    prepared = prepare_planning_problem(ItineraryPlannerInput.model_validate(raw))
    routing = asyncio.run(
        build_routing_problem(
            prepared,
            matrix_provider or GeneratedMatrixProvider(asymmetric=True),
            XanhSmTransportCostEstimator(),
        )
    )
    return prepared, routing


def test_beam_uses_adaptive_global_time_budgets() -> None:
    config = BeamSearchConfig()

    assert config.resolved_time_limit_seconds(1) == 10.0
    assert config.resolved_time_limit_seconds(3) == 20.0
    assert config.resolved_time_limit_seconds(4) == 30.0
    assert BeamSearchConfig(time_limit_seconds=2.5).resolved_time_limit_seconds(7) == 2.5


def test_rejects_two_restaurants_as_adjacent_nodes() -> None:
    raw = payload(
        foods=[food("restaurant_a"), food("restaurant_b")],
        places=[candidate("museum")],
    )
    prepared, _ = prepare_and_route(raw)

    first = prepared.candidate_by_id["restaurant_a"]
    second = prepared.candidate_by_id["restaurant_b"]

    assert is_restaurant_to_restaurant(first, second)


def test_matrix_marks_restaurant_to_restaurant_cells() -> None:
    first = food("restaurant_a")
    second = food("restaurant_b")
    place = candidate("museum")
    first["coordinates"] = {"latitude": 21.01, "longitude": 105.80}
    second["coordinates"] = {"latitude": 21.02, "longitude": 105.81}
    place["coordinates"] = {"latitude": 21.03, "longitude": 105.82}
    prepared, routing = prepare_and_route(
        payload(foods=[first, second], places=[place])
    )

    first_node = routing.candidate_to_matrix_node["restaurant_a"]
    second_node = routing.candidate_to_matrix_node["restaurant_b"]
    place_node = routing.candidate_to_matrix_node["museum"]
    assert routing.matrix.cell(first_node, second_node).food_to_food is True
    assert routing.matrix.cell(first_node, place_node).food_to_food is False


def test_long_transition_requires_quality_exception() -> None:
    config = BeamSearchConfig()

    assert long_transition_allowed(
        distance_meters=10_000,
        distance_q3=8_000,
        adjusted_rating=4.2,
        review_count=500,
        review_q3=400,
        config=config,
    )


def test_travelplace_quality_and_unique_daily_coverage_are_prioritized() -> None:
    raw = payload(
        places=[candidate("travel_a"), candidate("travel_b")],
        foods=[food()],
    )
    prepared, _ = prepare_and_route(raw, GeneratedMatrixProvider())
    config = BeamSearchConfig()
    quality = {candidate_id: 1.0 for candidate_id in prepared.candidate_by_id}
    empty = _DayState()
    first_score = candidate_score(
        prepared,
        prepared.candidate_by_id["travel_a"],
        empty,
        600,
        None,
        quality,
        config,
    )
    one_travel = _DayState(
        stops=(ScheduledStop("travel_a", 1, 600, 660, None),),
    )
    second_score = candidate_score(
        prepared,
        prepared.candidate_by_id["travel_b"],
        one_travel,
        700,
        None,
        quality,
        config,
    )

    assert second_score > first_score
    assert not long_transition_allowed(
        distance_meters=10_000,
        distance_q3=8_000,
        adjusted_rating=2.9,
        review_count=500,
        review_q3=400,
        config=config,
    )


def test_category_priority_prefers_leisure_diversity() -> None:
    three_drinks = category_sort_key(0, 0, 3, 0, 1, 100, 0)
    two_drinks_and_entertainment = category_sort_key(0, 0, 2, 1, 2, 100, 0)

    assert two_drinks_and_entertainment > three_drinks


def test_repetition_priority_is_entertainment_then_drink_then_restaurant() -> None:
    raw = payload(
        places=[candidate("museum")],
        foods=[food("restaurant")],
        entertainment_items=[
            {
                **candidate("show"),
                "entityType": "entertainment",
            },
            {
                **candidate("dessert_bar"),
                "entityType": "drink_dessert",
            },
        ],
    )
    prepared, _ = prepare_and_route(raw)
    repeated_entertainment = (
        ScheduledStop("show", 1, 600, 660, None),
        ScheduledStop("show", 1, 700, 760, None),
    )
    repeated_drink = (
        ScheduledStop("dessert_bar", 1, 600, 660, None),
        ScheduledStop("dessert_bar", 1, 700, 760, None),
    )
    repeated_restaurant = (
        ScheduledStop("restaurant", 1, 600, 660, None),
        ScheduledStop("restaurant", 1, 700, 760, None),
    )

    assert (
        repetition_sort_key(prepared, repeated_restaurant)
        > repetition_sort_key(prepared, repeated_drink)
        > repetition_sort_key(prepared, repeated_entertainment)
    )


def test_transition_window_keeps_waiting_and_visit_inside_window() -> None:
    result = fit_transition_window(
        arrival_minute=540,
        duration_minutes=45,
        windows=((570, 660),),
        max_wait_minutes=60,
    )

    assert result == (570, 615)


def test_beam_pruning_keeps_priority_state_before_higher_utility_state() -> None:
    raw = payload(
        places=[
            candidate("requested", priority="user_input"),
            candidate("optional"),
        ]
    )
    prepared, _ = prepare_and_route(raw)
    priority_state = _DayState(
        stops=(ScheduledStop("requested", 1, 600, 660, None),),
        selected_ids=frozenset({"requested"}),
        priority_ids=frozenset({"requested"}),
        score=1,
    )
    utility_state = _DayState(
        stops=(ScheduledStop("optional", 1, 600, 660, None),),
        selected_ids=frozenset({"optional"}),
        score=10_000,
    )

    selected = prune_day_states(
        [utility_state, priority_state],
        width=1,
        problem=prepared,
    )

    assert selected == (priority_state,)


def test_beam_search_prefers_plan_with_three_distinct_restaurants() -> None:
    raw = payload(
        places=[candidate("museum"), candidate("park")],
        foods=[
            food("breakfast_place", supported_meals=["breakfast"]),
            food("lunch_place", supported_meals=["lunch"]),
            food("dinner_place", supported_meals=["dinner"]),
        ],
    )
    prepared, routing = prepare_and_route(raw, GeneratedMatrixProvider())

    result = optimize_beam_search(
        prepared,
        routing,
        config=BeamSearchConfig(beam_width=8),
    )
    evaluation = evaluate_plan(prepared, routing, result)

    assert evaluation.count_restaurant == 3


def test_beam_fills_missing_restaurants_in_lunch_dinner_windows() -> None:
    raw = payload(
        places=[candidate("museum"), candidate("park")],
        foods=[
            food("breakfast_restaurant", supported_meals=["breakfast"]),
            food("lunch_restaurant", supported_meals=["lunch"]),
            food(
                "dinner_drink", supported_meals=["dinner"], venue_type="drink_dessert"
            ),
            food("fill_restaurant", supported_meals=["breakfast"]),
        ],
    )
    prepared, routing = prepare_and_route(raw)

    result = optimize_beam_search(prepared, routing, config=BeamSearchConfig())

    evaluation = evaluate_plan(prepared, routing, result)
    assert evaluation.count_restaurant == 3
    optional_restaurant = next(
        stop
        for stop in result.scheduled_stops
        if stop.meal_type is None
        and is_restaurant(prepared.candidate_by_id[stop.place_id])
    )
    assert (
        11 * 60 <= optional_restaurant.start_minute < 13 * 60
        or 18 * 60 <= optional_restaurant.start_minute < 20 * 60
    )
    ordered = sorted(result.scheduled_stops, key=lambda stop: stop.start_minute)
    assert all(
        not is_restaurant(prepared.candidate_by_id[left.place_id])
        or not is_restaurant(prepared.candidate_by_id[right.place_id])
        for left, right in zip(ordered, ordered[1:])
    )


def test_beam_only_blocks_repeated_travelplaces_across_days() -> None:
    raw = payload(
        days=2,
        places=[candidate(f"museum_{index}") for index in range(1, 7)],
        foods=[
            food("breakfast_place", supported_meals=["breakfast"]),
            food("lunch_place", supported_meals=["lunch"]),
            food("dinner_place", supported_meals=["dinner"]),
        ],
    )
    prepared, routing = prepare_and_route(raw)

    result = optimize_beam_search(
        prepared,
        routing,
        config=BeamSearchConfig(beam_width=16, max_stops_per_day=5),
    )

    travelplaces_by_day = {
        day: {
            stop.place_id
            for stop in result.scheduled_stops
            if stop.day == day
            and is_travelplace(prepared.candidate_by_id[stop.place_id])
        }
        for day in (1, 2)
    }
    restaurants_by_day = {
        day: {
            stop.place_id
            for stop in result.scheduled_stops
            if stop.day == day
            and is_restaurant(prepared.candidate_by_id[stop.place_id])
        }
        for day in (1, 2)
    }

    assert not travelplaces_by_day[1] & travelplaces_by_day[2]
    assert restaurants_by_day[1] & restaurants_by_day[2]


def test_beam_backtracks_day_combination_for_three_days() -> None:
    raw = payload(
        days=3,
        places=[candidate(f"museum_{index}") for index in range(1, 13)],
        foods=[
            food("breakfast_place", supported_meals=["breakfast"]),
            food("lunch_place", supported_meals=["lunch"]),
            food("dinner_place", supported_meals=["dinner"]),
        ],
    )
    prepared, routing = prepare_and_route(raw, GeneratedMatrixProvider())

    result = optimize_beam_search(
        prepared,
        routing,
        config=BeamSearchConfig(
            beam_width=16,
            combination_beam_width=16,
            max_stops_per_day=7,
        ),
    )

    travelplace_ids = [
        stop.place_id
        for stop in result.scheduled_stops
        if is_travelplace(prepared.candidate_by_id[stop.place_id])
    ]
    assert {stop.day for stop in result.scheduled_stops} == {1, 2, 3}
    assert len(travelplace_ids) == len(set(travelplace_ids))
    assert len(travelplace_ids) >= 12


def test_beam_returns_diverse_partial_fallback_when_meal_is_missing() -> None:
    expensive_food = food(
        "expensive_food", supported_meals=["breakfast", "lunch", "dinner"]
    )
    expensive_food["price"]["cost"] = 10_000_000
    raw = payload(
        places=[candidate("museum_a"), candidate("museum_b")],
        foods=[expensive_food],
    )
    prepared, routing = prepare_and_route(raw, GeneratedMatrixProvider())

    result = optimize_beam_search(
        prepared,
        routing,
        config=BeamSearchConfig(
            beam_width=8,
            max_stops_per_day=4,
            time_limit_seconds=0.2,
        ),
    )

    assert result.status == "PARTIAL"
    assert result.scheduled_stops
    assert any(
        is_travelplace(prepared.candidate_by_id[stop.place_id])
        for stop in result.scheduled_stops
    )
