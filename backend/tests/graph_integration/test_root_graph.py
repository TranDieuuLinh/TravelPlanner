import asyncio
from uuid import uuid4

from app.orchestration.root_graph import create_root_graph
from app.shared.contracts.place import Coordinates, PlaceCandidate


def test_planning_flow_runs_across_modules() -> None:
    graph = create_root_graph()
    thread_id = str(uuid4())

    result = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "request-1",
                "message": "Lập kế hoạch ở Đà Nẵng trong 2 ngày",
                "supplied_candidates": [
                    PlaceCandidate(
                        name="Bảo tàng Đà Nẵng",
                        coordinates=Coordinates(
                            latitude=16.0678,
                            longitude=108.2208,
                        ),
                    )
                ],
            },
            config={"configurable": {"thread_id": thread_id}},
        )
    )

    assert result["decision"].route == "explorer"
    assert result["itinerary"].intent.destination == "Đà Nẵng"
    assert len(result["itinerary"].days) == 2


def test_planning_flow_returns_clarification() -> None:
    graph = create_root_graph()

    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "request-2", "message": "Lập kế hoạch 2 ngày"},
            config={"configurable": {"thread_id": str(uuid4())}},
        )
    )

    assert result.get("itinerary") is None
    assert result["clarification_question"] == "Bạn muốn đi đến đâu?"
