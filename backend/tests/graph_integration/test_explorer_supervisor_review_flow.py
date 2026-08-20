import asyncio
from uuid import uuid4

from app.orchestration.root_graph import create_root_graph


def invoke(graph, thread_id: str, message: str, turn: int):
    return asyncio.run(
        graph.ainvoke(
            {"request_id": f"review-{turn}", "message": message},
            config={"configurable": {"thread_id": thread_id}},
        )
    )


def test_missing_destination_then_defaults_then_acceptance() -> None:
    graph = create_root_graph()
    thread_id = str(uuid4())

    missing = invoke(graph, thread_id, "Lập kế hoạch 2 ngày", 1)
    assert missing["explorer_review"]["kind"] == "missing_fields"
    assert missing.get("place_output") is None
    assert missing["clarification_question"] == "Bạn muốn đi tỉnh hoặc thành phố nào?"

    defaults = invoke(graph, thread_id, "Hà Nội", 2)
    assert defaults["explorer_review"]["kind"] == "defaults_proposed"
    assert defaults["explorer_output"].days == 2
    assert defaults["explorer_output"].budget.target_amount == 1_172_432
    assert defaults["explorer_review"]["defaultedFields"] == [
        "budget",
        "people",
        "shortPreferences",
    ]
    assert "shortAvoids" not in defaults["explorer_review"]["tripContext"]
    assert defaults.get("place_output") is None

    accepted = invoke(graph, thread_id, "OK", 3)
    assert accepted["explorer_review"]["kind"] == "ready_for_execution"
    assert accepted.get("pending_explorer_review") is None
    assert accepted["clarification_question"] is None
    assert "FinalItineraryPlanner" in accepted["response"]


def test_user_edit_applies_patch_and_executes_without_second_review() -> None:
    graph = create_root_graph()
    thread_id = str(uuid4())
    invoke(graph, thread_id, "Lập kế hoạch Hà Nội", 1)

    result = invoke(graph, thread_id, "Đi 4 ngày, 3 người", 2)

    assert result["explorer_review"]["kind"] == "ready_for_execution"
    assert result["explorer_output"].days == 4
    assert result["explorer_output"].people.adults == 3
    assert result["clarification_question"] is None


def test_fully_explicit_context_skips_default_review() -> None:
    graph = create_root_graph()
    result = invoke(
        graph,
        str(uuid4()),
        (
            "Lập kế hoạch Hà Nội 4 ngày cho 3 người, "
            "budget 6 triệu/người, thích văn hóa"
        ),
        1,
    )

    assert result["explorer_review"]["kind"] == "ready_for_execution"
    assert result.get("pending_explorer_review") is None
    assert "FinalItineraryPlanner" in result["response"]
