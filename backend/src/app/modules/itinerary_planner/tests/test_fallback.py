import asyncio

from app.modules.itinerary_planner.fallback import BeamFirstFallbackPlanner


class StubGraph:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def ainvoke(self, payload, **kwargs):
        self.calls += 1
        return self.result


def test_beam_error_uses_hybrid_fallback_and_adds_warning() -> None:
    beam = StubGraph(
        {"error": "no itinerary", "error_code": "beam_search_infeasible"}
    )
    hybrid = StubGraph({"output": {"warnings": []}, "warnings": []})
    planner = BeamFirstFallbackPlanner(beam, hybrid)

    result = asyncio.run(planner.ainvoke({"input": {}}))

    assert beam.calls == 1
    assert hybrid.calls == 1
    assert result["warnings"] == [
        "Beam Search was not used successfully (beam_search_infeasible); "
        "Hybrid planner was used as fallback."
    ]
    assert result["output"]["warnings"] == result["warnings"]


def test_shared_preflight_error_does_not_run_hybrid_fallback() -> None:
    beam = StubGraph(
        {
            "error": "missing breakfast",
            "error_code": "missing_meal_coverage",
        }
    )
    hybrid = StubGraph({"output": {"warnings": []}, "warnings": []})
    planner = BeamFirstFallbackPlanner(beam, hybrid)

    result = asyncio.run(planner.ainvoke({"input": {}}))

    assert result["error_code"] == "missing_meal_coverage"
    assert hybrid.calls == 0
