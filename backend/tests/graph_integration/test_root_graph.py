import asyncio
from uuid import uuid4

from app.orchestration.root_graph import create_root_graph


def test_legacy_planning_flow_does_not_generate_a_fake_itinerary() -> None:
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

    assert result["decision"].route == "finish"
    assert result.get("itinerary") is None
    assert result["clarification_question"] == (
        "Ngân sách dự kiến cho chuyến đi là bao nhiêu?"
    )


def test_planning_flow_returns_clarification() -> None:
    graph = create_root_graph()

    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "request-2", "message": "Lập kế hoạch 2 ngày"},
            config={"configurable": {"thread_id": str(uuid4())}},
        )
    )

    assert result.get("itinerary") is None
    assert result["clarification_question"] == (
        "Để tiếp tục, Penguin cần thêm:\n"
        "1. Bạn muốn đi tỉnh hoặc thành phố nào?\n"
        "2. Ngân sách dự kiến cho chuyến đi là bao nhiêu?"
    )


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

    assert result["decision"].route == "finish"
    assert result["explorer_output"].input_adm == "Huế"
    assert result["clarification_question"] == (
        "Để tiếp tục, Penguin cần thêm:\n"
        "1. Bạn muốn đi trong bao nhiêu ngày?\n"
        "2. Ngân sách dự kiến cho chuyến đi là bao nhiêu?"
    )


def test_agent_questions_are_answered_through_supervisor_on_next_turn() -> None:
    graph = create_root_graph()
    config = {"configurable": {"thread_id": str(uuid4())}}

    first = asyncio.run(
        graph.ainvoke(
            {
                "request_id": "context-request-1",
                "message": "Lập kế hoạch ở Đà Nẵng trong 3 ngày",
            },
            config=config,
        )
    )
    assert [item["field"] for item in first["pending_user_context"]] == ["budget"]

    second = asyncio.run(
        graph.ainvoke(
            {"request_id": "context-request-2", "message": "Ngân sách 5 triệu"},
            config=config,
        )
    )
    assert second["decision"].route == "explorer"
    assert second["pending_user_context"] == []


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


def test_same_thread_routes_english_destination_follow_up_to_information() -> None:
    graph = create_root_graph()
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    asyncio.run(
        graph.ainvoke(
            {"request_id": "context-info-1", "message": "Tôi muốn biết thêm về Hà Nội."},
            config=config,
        )
    )
    result = asyncio.run(
        graph.ainvoke(
            {"request_id": "context-info-2", "message": "Hoàn Kiếm Lake thì sao?"},
            config=config,
        )
    )

    assert result["decision"].route == "information_finder"
