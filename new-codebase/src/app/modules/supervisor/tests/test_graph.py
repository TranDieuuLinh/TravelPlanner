import asyncio

from app.modules.supervisor.public import build_supervisor_graph


def test_routes_information_request() -> None:
    graph = build_supervisor_graph()

    result = asyncio.run(
        graph.ainvoke(
            {"message": "Thời tiết ở Hà Nội là gì?", "has_itinerary": False}
        )
    )

    assert result["decision"].route == "information_finder"


def test_routes_structured_edit() -> None:
    graph = build_supervisor_graph()

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
