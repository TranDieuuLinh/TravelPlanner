import asyncio
from types import SimpleNamespace

from app.modules.itinerary_planner import nodes
from app.modules.itinerary_planner.optimizer import ObjectiveWeights, SolverConfig
from app.modules.itinerary_planner.optimizer.solver import OptimizationError


def baseline_result():
    return SimpleNamespace(
        selected_ids=(),
        scheduled_stops=(),
        selected_accommodation_id=None,
    )


def test_infeasible_locked_repair_replans_all_days(monkeypatch) -> None:
    fallback_result = object()

    def fail_locked_repair(*args, **kwargs):
        raise OptimizationError("INFEASIBLE", "priority")

    monkeypatch.setattr(nodes, "optimize_itinerary", fail_locked_repair)
    monkeypatch.setattr(
        nodes,
        "optimize_hybrid_itinerary",
        lambda *args, **kwargs: fallback_result,
    )

    result, repair_scope, warning = asyncio.run(
        nodes._repair_optimization(
            SimpleNamespace(trip=SimpleNamespace(days=3)),
            object(),
            baseline_result(),
            frozenset({2}),
            SolverConfig(),
            ObjectiveWeights(),
        )
    )

    assert result is fallback_result
    assert repair_scope == frozenset({1, 2, 3})
    assert warning is not None and "relaxed" in warning


def test_unknown_locked_repair_replans_all_days(monkeypatch) -> None:
    fallback_result = object()

    def time_out(*args, **kwargs):
        raise OptimizationError("UNKNOWN", "priority")

    monkeypatch.setattr(nodes, "optimize_itinerary", time_out)
    monkeypatch.setattr(
        nodes,
        "optimize_hybrid_itinerary",
        lambda *args, **kwargs: fallback_result,
    )

    result, repair_scope, warning = asyncio.run(
        nodes._repair_optimization(
            SimpleNamespace(trip=SimpleNamespace(days=2)),
            object(),
            baseline_result(),
            frozenset({1}),
            SolverConfig(),
            ObjectiveWeights(),
        )
    )

    assert result is fallback_result
    assert repair_scope == frozenset({1, 2})
    assert warning is not None and "compact per-day" in warning
