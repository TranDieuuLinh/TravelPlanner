import pytest

from app.modules.itinerary_planner.optimizer.solver import OptimizationError
from app.modules.itinerary_planner.policies import MAX_INTER_STOP_WAIT_MINUTES
from app.modules.itinerary_planner.routing_models import MatrixCell, TravelMatrix
from app.modules.itinerary_planner.tests.factories import candidate, food, payload
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    base_payload,
    meal_candidates,
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

    result, _, routing = solve_payload(raw)

    assert result.user_input_count == 1
    assert {
        stop.meal_type.value for stop in result.scheduled_stops if stop.meal_type
    } == {
        "breakfast",
        "lunch",
        "dinner",
    }
    meals = {
        stop.meal_type.value: stop for stop in result.scheduled_stops if stop.meal_type
    }
    assert meals["breakfast"].start_minute <= 600
    assert meals["lunch"].start_minute - meals["breakfast"].start_minute >= 180
    assert meals["dinner"].start_minute - meals["lunch"].start_minute >= 300
    museum_stop = next(
        stop for stop in result.scheduled_stops if stop.place_id == "museum"
    )
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


def test_meals_are_separated_by_activity_and_route_wait_is_bounded() -> None:
    result, prepared, routing = solve_payload(base_payload())
    food_ids = {food.place_id for food in prepared.valid_food}
    stops = {(stop.place_id, stop.day): stop for stop in result.scheduled_stops}

    waits = []
    for arc in result.selected_arcs:
        assert not (arc.origin_id in food_ids and arc.destination_id in food_ids)
        wait = (
            stops[(arc.destination_id, arc.day)].start_minute
            - stops[(arc.origin_id, arc.day)].end_minute
            - routing.travel_by_candidate_pair[
                (arc.origin_id, arc.destination_id)
            ].safe_minutes
        )
        waits.append(wait)
        assert 0 <= wait <= MAX_INTER_STOP_WAIT_MINUTES
    assert any(wait > 15 for wait in waits)
    assert result.objective_components["idleWaitingCost"] > 0


def test_schedule_is_infeasible_without_activity_between_meals() -> None:
    raw = payload(foods=meal_candidates())

    with pytest.raises(OptimizationError, match="INFEASIBLE"):
        solve_payload(raw)


def test_drink_dessert_is_limited_and_cannot_fill_adjacent_meals() -> None:
    breakfast_drink = food(
        "breakfast_drink",
        supported_meals=["breakfast"],
        venue_type="drink_dessert",
    )
    lunch_drink = food(
        "lunch_drink",
        supported_meals=["lunch"],
        venue_type="drink_dessert",
    )
    lunch_drink["priority"] = "user_input"
    lunch_restaurant = food(
        "lunch_restaurant",
        supported_meals=["lunch"],
    )
    dinner_restaurant = food(
        "dinner_restaurant",
        supported_meals=["dinner"],
    )
    raw = payload(
        places=base_payload()["places"],
        foods=[
            breakfast_drink,
            lunch_drink,
            lunch_restaurant,
            dinner_restaurant,
        ],
    )

    result, prepared, _ = solve_payload(raw)

    selected = {
        stop.meal_type.value: prepared.candidate_by_id[stop.place_id]
        for stop in result.scheduled_stops
        if stop.meal_type
    }
    assert selected["breakfast"].venue_type.value == "drink_dessert"
    assert selected["lunch"].venue_type.value == "restaurant"
    assert sum(
        candidate.venue_type.value == "drink_dessert"
        for candidate in selected.values()
    ) <= 2


def test_three_drink_dessert_meals_are_infeasible() -> None:
    raw = payload(
        places=base_payload()["places"],
        foods=[
            food(
                f"{meal}_drink",
                supported_meals=[meal],
                venue_type="drink_dessert",
            )
            for meal in ("breakfast", "lunch", "dinner")
        ],
    )

    with pytest.raises(OptimizationError, match="INFEASIBLE"):
        solve_payload(raw)


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
    assert [item.name for item in result.passes] == ["priority", "utility"]
    assert all(item.status in {"OPTIMAL", "FEASIBLE"} for item in result.passes)


def test_budget_can_make_full_schedule_infeasible() -> None:
    raw = base_payload()
    raw["trip"]["budget"]["amount"] = 1
    for meal in raw["food"]:
        meal["price"]["cost"] = 100_000

    with pytest.raises(OptimizationError, match="INFEASIBLE"):
        solve_payload(raw)


def test_estimated_budget_is_a_soft_target() -> None:
    raw = base_payload()
    raw["trip"]["budget"] = {
        "amount": 1,
        "currency": "VND",
        "source": "estimated_daily_cost",
        "dailyEstimate": {
            "accommodation": 0,
            "food": 1,
            "localTransport": 0,
            "activities": 0,
            "total": 1,
        },
        "profileVersion": "test-v1",
    }
    for meal in raw["food"]:
        meal["price"]["cost"] = 100_000

    result, _, _ = solve_payload(raw)

    assert result.total_cost_per_person > raw["trip"]["budget"]["amount"]


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
    raw["trip"]["party"] = {"adults": 3, "kids": 0}
    shared_coordinates = {"latitude": 21.02, "longitude": 105.84}
    for item in [*raw["places"], *raw["food"]]:
        item["coordinates"] = shared_coordinates
    for meal in raw["food"]:
        meal["price"]["cost"] = 100

    result, _, _ = solve_payload(raw)

    assert result.total_cost_per_person == 300


class CoordinateDistanceMatrixProvider:
    async def matrix(self, locations, profile):
        rows = []
        for origin in locations:
            row = []
            for destination in locations:
                distance = round(
                    abs(origin.longitude - destination.longitude) * 100_000
                )
                row.append(
                    MatrixCell(
                        duration_seconds=distance / 500,
                        distance_meters=distance,
                        reachable=True,
                    )
                )
            rows.append(tuple(row))
        return TravelMatrix(
            node_ids=tuple(item.node_id for item in locations),
            cells=tuple(rows),
            profile=profile,
            provider="coordinate-test",
            provider_version="v1",
        )


def test_selects_accommodation_by_night_cost_and_route_distance() -> None:
    raw = base_payload(days=2)
    raw["accommodations"] = [
        {
            "placeId": "hotel:near",
            "name": "Near Hotel",
            "coordinates": {"latitude": 21.02, "longitude": 105.84},
            "pricePerNight": {"cost": 600_000, "currency": "VND"},
        },
        {
            "placeId": "hotel:far",
            "name": "Far Hotel",
            "coordinates": {"latitude": 21.02, "longitude": 106.44},
            "pricePerNight": {"cost": 100_000, "currency": "VND"},
        },
    ]

    result, prepared, _ = solve_payload(
        raw,
        matrix_provider=CoordinateDistanceMatrixProvider(),
    )

    assert prepared.accommodation_nights == 1
    assert result.selected_accommodation_id == "hotel:near"
    assert len(result.accommodation_transfers) == 2


def test_selects_lower_priced_accommodation_when_route_cost_is_equal() -> None:
    raw = base_payload(days=2)
    coordinates = {"latitude": 21.02, "longitude": 105.84}
    raw["accommodations"] = [
        {
            "placeId": "hotel:expensive",
            "name": "Expensive Hotel",
            "coordinates": coordinates,
            "pricePerNight": {"cost": 900_000, "currency": "VND"},
        },
        {
            "placeId": "hotel:budget",
            "name": "Budget Hotel",
            "coordinates": coordinates,
            "pricePerNight": {"cost": 300_000, "currency": "VND"},
        },
    ]

    result, _, _ = solve_payload(raw)

    assert result.selected_accommodation_id == "hotel:budget"
