import asyncio

from app.modules.explorer.public import build_explorer_graph


def test_extracts_destination_and_days() -> None:
    graph = build_explorer_graph()

    result = asyncio.run(
        graph.ainvoke({"message": "Lập kế hoạch ở Huế trong 3 ngày"})
    )

    assert result["output"].intent.destination == "Huế"
    assert result["output"].intent.days == 3


def test_requests_missing_destination() -> None:
    graph = build_explorer_graph()

    result = asyncio.run(graph.ainvoke({"message": "Lập kế hoạch 3 ngày"}))

    assert result["output"].intent is None
    assert result["output"].missing_fields == ["destination"]
