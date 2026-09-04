import asyncio

from app.modules.itinerary_planner.public import ItineraryPlannerInput
from app.orchestration.nodes import RootNodes


class PlannerGraph:
    def __init__(self, days):
        self.days = days

    async def ainvoke(self, graph_input):
        assert isinstance(graph_input["input"], ItineraryPlannerInput)
        return {
            "output": {
                "destination": "Hanoi",
                "timezone": "Asia/Ho_Chi_Minh",
                "people": graph_input["input"].trip.people,
                "days": self.days,
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
    days = [
        {
            "day": 1,
            "date": "2026-08-20",
            "stops": [
                {
                    "itemId": "planner:1:place-1",
                    "placeId": "place-1",
                    "name": "Hồ Hoàn Kiếm",
                    "kind": "place",
                    "priority": "special_experience",
                    "startMinute": 480,
                    "endMinute": 540,
                    "durationMinutes": 60,
                    "coordinates": {"latitude": 21.0285, "longitude": 105.8542},
                    "notes": {
                        "text": "Nên đến trước 8 giờ để tránh đông.",
                        "sourceType": "url",
                        "sourceUrl": "https://example.test/video",
                    },
                    "costPerPerson": 0,
                }
            ],
            "legs": [],
            "activityMinutes": 60,
            "travelMinutes": 0,
            "costPerPerson": 0,
            "costBreakdown": {
                "accommodation": 0,
                "food": 0,
                "localTransport": 0,
                "activities": 0,
                "misc": 0,
                "total": 0,
                "currency": "VND",
            },
        }
    ]
    nodes = RootNodes(itinerary_planner_graph=PlannerGraph(days))

    result = asyncio.run(nodes.run_itinerary_planner({"planner_input": planner_input}))

    assert result["planner_output"].destination == "Hanoi"
    assert result.get("itinerary") is None
    assert result["response"] == "Đã tối ưu lịch trình thành công."

    finished = asyncio.run(nodes.finish(result))
    assert finished["response"] == "Đã tối ưu lịch trình thành công."


def test_root_rejects_success_when_requested_days_are_empty() -> None:
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
    nodes = RootNodes(itinerary_planner_graph=PlannerGraph([]))

    result = asyncio.run(nodes.run_itinerary_planner({"planner_input": planner_input}))

    assert result.get("planner_output") is None
    assert result["response"].startswith("Itinerary planning stopped:")
    assert "every requested day" in result["warnings"][-1]
