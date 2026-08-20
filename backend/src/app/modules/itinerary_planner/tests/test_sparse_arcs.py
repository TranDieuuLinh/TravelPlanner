from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.routing import (
    DEFAULT_NEIGHBOR_LIMIT,
    build_sparse_arcs,
    feasible_arc_days,
)
from app.modules.itinerary_planner.routing_models import SafeTravel
from app.modules.itinerary_planner.sparse_arc_policy import (
    MEAL_ACCESS_NEIGHBOR_LIMIT,
    meal_access_pairs,
)
from app.modules.itinerary_planner.tests.factories import candidate, payload


def make_problem():
    places = []
    for index in range(5):
        place = candidate(f"place_{index}")
        place["coordinates"] = {
            "latitude": 21.0 + index / 100,
            "longitude": 105.8,
        }
        places.append(place)
    places[0]["priority"] = "user_input"
    places[0]["relationships"] = ["place_4"]
    return prepare_planning_problem(
        ItineraryPlannerInput.model_validate(payload(places=places))
    )


def test_default_neighbor_limit_is_ten() -> None:
    assert DEFAULT_NEIGHBOR_LIMIT == 10


def test_sparse_arcs_keep_relationship_outside_nearest_k() -> None:
    problem = make_problem()
    travel = {
        (origin, destination): SafeTravel(
            raw_minutes=distance,
            safe_minutes=distance,
            distance_meters=distance * 100,
            transport_cost_per_person=distance * 10,
        )
        for origin in problem.candidate_by_id
        for destination in problem.candidate_by_id
        if origin != destination
        for distance in [abs(hash(origin) - hash(destination)) % 20 + 1]
    }
    travel[("place_0", "place_4")] = SafeTravel(100, 100, 10_000, 1_000)

    arcs, _ = build_sparse_arcs(problem, travel, neighbor_limit=1)
    real_arcs = [arc for arc in arcs if not arc.is_virtual]

    relationship = next(
        arc
        for arc in real_arcs
        if (arc.origin_id, arc.destination_id) == ("place_0", "place_4")
    )
    assert "relationship" in relationship.forced_reasons
    assert len(real_arcs) < len(problem.candidate_by_id) ** 2


def test_arc_pruning_respects_time_order() -> None:
    early = candidate(
        "early",
        opening_hours={"1": [{"startMinute": 540, "endMinute": 600}]},
        duration_minutes=60,
    )
    late = candidate(
        "late",
        opening_hours={"1": [{"startMinute": 660, "endMinute": 720}]},
        duration_minutes=60,
    )
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(payload(places=[early, late]))
    )

    assert feasible_arc_days(problem, "early", "late", 30) == frozenset({1})
    assert feasible_arc_days(problem, "late", "early", 30) == frozenset()


def test_unreachable_priority_is_warned_and_never_estimated() -> None:
    problem = make_problem()
    travel = {
        (origin, destination): SafeTravel(10, 15, 1_000, 100)
        for origin in problem.candidate_by_id
        for destination in problem.candidate_by_id
        if origin != destination and "place_0" not in {origin, destination}
    }

    arcs, warnings = build_sparse_arcs(problem, travel, neighbor_limit=2)

    assert not any(
        "place_0" in {arc.origin_id, arc.destination_id}
        for arc in arcs
        if not arc.is_virtual
    )
    assert any("unreachable_priority: place_0" in warning for warning in warnings)
    assert any(arc.origin_id == "__start__:1" for arc in arcs)
    assert any(arc.destination_id == "__end__:1" for arc in arcs)


def test_meal_access_keeps_multiple_activity_neighbors_per_food() -> None:
    problem = make_problem()
    food_ids = {item.place_id for item in problem.valid_food}
    activity_ids = set(problem.candidate_by_id) - food_ids
    cross_pairs = {
        (origin, destination)
        for origin in problem.candidate_by_id
        for destination in problem.candidate_by_id
        if origin != destination
        and ((origin in food_ids) != (destination in food_ids))
    }
    feasible = {pair: frozenset({1}) for pair in cross_pairs}
    travel = {
        pair: SafeTravel(10, 10, 1_000, 100)
        for pair in cross_pairs
    }

    selected = meal_access_pairs(
        feasible,
        travel,
        problem.feasible_days,
        food_ids,
        activity_ids,
    )

    expected = min(MEAL_ACCESS_NEIGHBOR_LIMIT, len(activity_ids))
    for food_id in food_ids:
        assert sum(pair[0] == food_id for pair in selected) >= expected
        assert sum(pair[1] == food_id for pair in selected) >= expected
