import asyncio

from app.modules.supervisor.contract import ClassifierResult
from app.modules.supervisor.public import SupervisorService, build_supervisor_graph
from app.shared.contracts.user_context import UserContextRequest


class FakeClassifier:
    async def classify(self, payload):
        route = "plan_editor" if payload.has_itinerary else "information_finder"
        return ClassifierResult(route=route, confidence=0.9, reason="test")


def test_routes_information_request() -> None:
    graph = build_supervisor_graph(SupervisorService(FakeClassifier()))

    result = asyncio.run(
        graph.ainvoke({"message": "Thời tiết ở Hà Nội là gì?", "has_itinerary": False})
    )

    assert result["decision"].route == "information_finder"


def test_routes_structured_edit() -> None:
    graph = build_supervisor_graph(SupervisorService(FakeClassifier()))

    result = asyncio.run(
        graph.ainvoke(
            {
                "message": "Cập nhật lịch trình",
                "has_itinerary": True,
                "has_edit_operation": True,
            }
        )
    )

    assert result["decision"].route == "plan_editor"


def test_turns_agent_context_request_into_user_question() -> None:
    graph = build_supervisor_graph(SupervisorService())
    request = UserContextRequest(
        field="budget",
        source_agent="place_checker",
        resume_route="explorer",
    )

    result = asyncio.run(
        graph.ainvoke({"message": "Lập kế hoạch", "user_context_requests": [request]})
    )

    assert result["decision"].route == "finish"
    assert result["decision"].clarification_question == (
        "Ngân sách dự kiến cho chuyến đi là bao nhiêu?"
    )
