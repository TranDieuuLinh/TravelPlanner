import asyncio

from app.modules.itinerary_planner.public import ItineraryPlannerInput
from app.orchestration.nodes import RootNodes


class PlannerGraph:
    async def ainvoke(self, graph_input):
        assert isinstance(graph_input["input"], ItineraryPlannerInput)
        return {
            "output": {
                "destination": "Hanoi",
                "timezone": "Asia/Ho_Chi_Minh",
                "days": [],
                "totalCostPerPerson": 0,
                "budgetPerPerson": 5000000,
                "currency": "VND",
                "solver": {
                    "status": "OPTIMAL",
                    "optimalityProven": True,
                    "objectiveValue": 0,
                    "objectivePolicyVersion": "test-v1",
                    "objectiveComponents": {},
                    "passes": [],
                    "planningTimeMs": 1,
                },
                "unscheduled": [],
                "discardedOptionalCount": 0,
                "warnings": [],
                "phaseTimingsMs": {"total": 1},
            },
            "warnings": [],
        }


def test_root_exposes_new_planner_output_without_legacy_conversion() -> None:
    planner_input = ItineraryPlannerInput.model_validate(
        {
            "trip": {
                "destination": "Hanoi",
                "days": 1,
                "startDate": "2026-08-20",
                "timezone": "Asia/Ho_Chi_Minh",
                "people": 1,
                "budget": {"amount": 5000000, "currency": "VND"},
                "preferences": [],
            },
            "places": [],
            "food": [],
        }
    )
    nodes = RootNodes(itinerary_planner_graph=PlannerGraph())

    result = asyncio.run(
        nodes.run_itinerary_planner({"planner_input": planner_input})
    )

    assert result["planner_output"].destination == "Hanoi"
    assert result.get("itinerary") is None
    assert result["response"] == "Itinerary was optimized successfully."
