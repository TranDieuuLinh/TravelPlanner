from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.hybrid.heuristic import full_day_candidate_ids
from app.modules.itinerary_planner.preprocessing import prepare_planning_problem
from app.modules.itinerary_planner.tests.factories import candidate, food, payload


def test_non_preferred_feasible_day_remains_in_full_day_reserve() -> None:
    places = [candidate(f"place_{index}") for index in range(9)]
    meals = [food(f"food_{index}") for index in range(4)]
    problem = prepare_planning_problem(
        ItineraryPlannerInput.model_validate(
            payload(days=3, places=places, foods=meals)
        )
    )
    candidate_id, reserve_day = next(
        (candidate_id, day)
        for candidate_id, feasible in problem.feasible_days.items()
        if candidate_id.startswith("place_")
        for day in feasible
        if day not in problem.preferred_days[candidate_id]
    )

    reserve = full_day_candidate_ids(
        problem,
        day=reserve_day,
        used_ids=frozenset(),
    )

    assert candidate_id in reserve
