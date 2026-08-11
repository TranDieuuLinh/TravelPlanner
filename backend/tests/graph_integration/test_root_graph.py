import asyncio
from uuid import uuid4

from app.orchestration.root_graph import create_root_graph


def test_planning_flow_runs_across_modules() -> None:
    graph = create_root_graph()
    thread_id = str(uuid4())

    result = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "request-1",
                "message": "Lập kế hoạch ở Đà Nẵng trong 2 ngày, tham quan Cầu Rồng",
            },
            config={"configurable": {"thread_id": thread_id}},
        )
    )

    assert result["decision"].route == "explorer"
    assert result["itinerary"].intent.destination == "Da Nang"
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
    assert result["clarification_question"] == "Bạn muốn đi tỉnh hoặc thành phố nào?"


def test_image_without_prompt_routes_to_explorer() -> None:
    graph = create_root_graph()
    result = asyncio.run(graph.ainvoke(
        {
            "request_id": "request-image",
            "message": "",
            "images": [{
                "fileName": "capture.png", "mimeType": "image/png",
                "ocrText": "Du lịch ở Huế, tham quan Đại Nội",
            }],
        },
        config={"configurable": {"thread_id": str(uuid4())}},
    ))

    assert result["decision"].route == "explorer"
    assert result["explorer_output"].input_adm == "Huế"


def test_same_thread_keeps_user_context_for_follow_up_routing() -> None:
    graph = create_root_graph()
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    asyncio.run(
        graph.ainvoke(
            {"request_id": "context-1", "message": "Tôi muốn biết về Hải Phòng."},
            config=config,
        )
    )
    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "context-2", "message": "Còn chỗ này thì sao?"},
            config=config,
        )
    )

    assert result["decision"].route == "information_finder"
    assert result.get("itinerary") is None
