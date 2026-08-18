from types import SimpleNamespace

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.popular_place_coverage import (
    build_popular_place_shortfall_cost,
    popular_place_ids,
)
from app.modules.itinerary_planner.optimizer.variables import PlannerVariables


def _place(place_id: str, rating: float, reviews: int):
    return SimpleNamespace(
        place_id=place_id,
        rating=rating,
        review_count=reviews,
    )


def test_popular_places_require_high_bayesian_rating_and_review_volume() -> None:
    problem = SimpleNamespace(
        valid_places=(
            _place("landmark", 4.7, 10_000),
            _place("moderate_landmark", 4.3, 1_974),
            _place("sparse_five_star", 5.0, 120),
            _place("widely_reviewed_low", 3.8, 20_000),
        )
    )

    assert popular_place_ids(problem) == frozenset(
        {"landmark", "moderate_landmark"}
    )


def test_popular_classification_is_stable_when_daily_pool_changes() -> None:
    landmark = _place("landmark", 4.3, 1_974)
    full_problem = SimpleNamespace(
        valid_places=(landmark, _place("excellent", 5.0, 50_000))
    )
    daily_problem = SimpleNamespace(
        valid_places=(landmark, _place("weak", 3.0, 1))
    )

    assert "landmark" in popular_place_ids(full_problem)
    assert "landmark" in popular_place_ids(daily_problem)


def test_daily_popular_target_is_soft_when_none_is_selected() -> None:
    model = cp_model.CpModel()
    variables = PlannerVariables()
    places = (
        _place("landmark_a", 4.7, 10_000),
        _place("landmark_b", 4.6, 8_000),
    )
    for candidate in places:
        assigned = variables.remember(
            model.NewBoolVar(f"assigned:{candidate.place_id}:1")
        )
        variables.assigned[(candidate.place_id, 1)] = assigned
    model.Add(variables.assigned[("landmark_a", 1)] == 0)
    model.Add(variables.assigned[("landmark_b", 1)] == 0)
    problem = SimpleNamespace(
        trip=SimpleNamespace(days=1),
        valid_places=places,
    )

    cost = build_popular_place_shortfall_cost(
        model,
        problem,
        variables,
        weight=1_800,
    )
    model.Minimize(cost)
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1

    assert solver.Solve(model) == cp_model.OPTIMAL
    assert solver.Value(cost) == 3_600
