import pytest

from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.tests.factories import candidate
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    base_payload,
    solve_payload,
)


def test_schedule_satisfies_meals_opening_route_and_per_person_budget() -> None:
    museum = candidate(
        "museum",
        priority="user_input",
        opening_hours={"1": [{"startMinute": 540, "endMinute": 720}]},
        duration_minutes=90,
    )
    museum["coordinates"] = {"latitude": 21.08, "longitude": 105.85}
    raw = base_payload(places=[museum])
    raw["trip"]["budget"]["amount"] = 1_000_000

    result, prepared, routing = solve_payload(raw)

    assert result.user_input_count == 1
    assert {stop.meal_type.value for stop in result.scheduled_stops if stop.meal_type} == {
        "breakfast",
        "lunch",
        "dinner",
    }
    museum_stop = next(stop for stop in result.scheduled_stops if stop.place_id == "museum")
    assert 540 <= museum_stop.start_minute
    assert museum_stop.end_minute <= 720
    assert museum_stop.end_minute - museum_stop.start_minute == 90
    assert result.total_cost_per_person <= raw["trip"]["budget"]["amount"]

    stops = {(stop.place_id, stop.day): stop for stop in result.scheduled_stops}
    travel = routing.travel_by_candidate_pair
    for arc in result.selected_arcs:
        assert stops[(arc.destination_id, arc.day)].start_minute >= (
            stops[(arc.origin_id, arc.day)].end_minute
            + travel[(arc.origin_id, arc.destination_id)].safe_minutes
        )


def test_lexicographic_passes_lock_user_then_url_count() -> None:
    first = candidate(
        "user_a",
        priority="user_input",
        opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
    )
    second = candidate(
        "user_b",
        priority="user_input",
        opening_hours={"1": [{"startMinute": 600, "endMinute": 660}]},
    )
    url = candidate(
        "url_place",
        priority="url",
        opening_hours={"1": [{"startMinute": 840, "endMinute": 930}]},
    )
    result, _, _ = solve_payload(base_payload(places=[first, second, url]))

    assert result.user_input_count == 1
    assert result.url_count == 1
    assert [item.name for item in result.passes] == ["user_input", "url", "utility"]
    assert all(item.status in {"OPTIMAL", "FEASIBLE"} for item in result.passes)


def test_budget_can_make_full_schedule_infeasible() -> None:
    raw = base_payload()
    raw["trip"]["budget"]["amount"] = 1
    for meal in raw["food"]:
        meal["price"]["cost"] = 100_000

    with pytest.raises(OptimizationError, match="INFEASIBLE"):
        solve_payload(raw)


def test_route_is_one_chain_without_candidate_subtour() -> None:
    places = [candidate(f"place_{index}", priority="user_input") for index in range(2)]
    result, _, _ = solve_payload(base_payload(places=places))

    selected_count = len(result.scheduled_stops)
    assert len(result.selected_arcs) == selected_count - 1
    outgoing = {arc.origin_id: arc.destination_id for arc in result.selected_arcs}
    assert len(outgoing) == len(result.selected_arcs)
    for origin in outgoing:
        seen = set()
        current = origin
        while current in outgoing:
            assert current not in seen
            seen.add(current)
            current = outgoing[current]


def test_candidate_prices_are_per_person_and_not_multiplied_by_people() -> None:
    raw = base_payload()
    raw["trip"]["people"] = 3
    shared_coordinates = {"latitude": 21.02, "longitude": 105.84}
    for meal in raw["food"]:
        meal["coordinates"] = shared_coordinates
        meal["price"]["cost"] = 100

    result, _, _ = solve_payload(raw)

    assert result.total_cost_per_person == 300
