from datetime import datetime, timezone

from app.modules.plans.routing.provider import TravelTimeMatrix
from app.modules.plans.solver.cluster_first_repair import ClusterFirstRepairSolver
from app.modules.plans.solver.contracts import CandidatePool, PlanningCandidate


def _activity(index: int, *, latitude: float | None = None) -> PlanningCandidate:
    return PlanningCandidate(
        candidate_id=f"place:{index}",
        name=f"Place {index}",
        kind="activity",
        duration_minutes=90,
        mandatory=True,
        latitude=latitude,
        longitude=105.8 + index / 100 if latitude is not None else None,
        source_order=index,
    )


class CountingMatrixProvider:
    def __init__(self) -> None:
        self.calls = 0

    def calculate(self, coordinates, *, transport_mode, departure_time):
        self.calls += 1
        size = len(coordinates)
        return TravelTimeMatrix(
            travel_times_seconds=[
                [0 if left == right else 10 * 60 for right in range(size)]
                for left in range(size)
            ],
            provider="test_matrix",
            fetched_at=datetime.now(timezone.utc),
        )


def test_unlocked_solver_opens_days_without_rerunning_matrix() -> None:
    provider = CountingMatrixProvider()
    solution = ClusterFirstRepairSolver().solve(
        CandidatePool(tuple(_activity(index, latitude=21.0) for index in range(1, 9))),
        requested_days=1,
        days_locked=False,
        matrix_provider=provider,
    )

    assert solution.day_count == 2
    assert solution.unscheduled_candidate_ids == ()
    assert provider.calls == 1
    assert set(solution.candidate_day) == {f"place:{index}" for index in range(1, 9)}


def test_locked_solver_keeps_overflow_visible() -> None:
    solution = ClusterFirstRepairSolver().solve(
        CandidatePool(tuple(_activity(index) for index in range(1, 9))),
        requested_days=1,
        days_locked=True,
    )

    assert solution.day_count == 1
    assert len(solution.unscheduled_candidate_ids) == 3


def test_meals_use_three_daily_anchors() -> None:
    meals = tuple(
        PlanningCandidate(
            candidate_id=f"meal:{index}",
            name=f"Meal {index}",
            kind="meal",
            duration_minutes=60,
            mandatory=True,
            source_order=index,
        )
        for index in range(1, 5)
    )

    solution = ClusterFirstRepairSolver().solve(
        CandidatePool(meals),
        requested_days=1,
        days_locked=False,
    )

    assert solution.day_count == 2
    assert [len(day.candidate_ids) for day in solution.days] == [3, 1]


def test_solver_is_deterministic_for_same_pool_and_matrix() -> None:
    pool = CandidatePool(tuple(_activity(index) for index in range(1, 8)))
    solver = ClusterFirstRepairSolver()

    first = solver.solve(pool, requested_days=2, days_locked=True)
    second = solver.solve(pool, requested_days=2, days_locked=True)

    assert first.days == second.days
    assert first.unscheduled_candidate_ids == second.unscheduled_candidate_ids
