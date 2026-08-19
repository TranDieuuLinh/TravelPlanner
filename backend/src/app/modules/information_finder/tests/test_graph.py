import asyncio

from app.modules.information_finder.public import build_information_finder_graph


def test_reports_truthful_unconfigured_fallback() -> None:
    graph = build_information_finder_graph()
    result = asyncio.run(graph.ainvoke({"query": "Giờ mở cửa bảo tàng"}))
    assert "Chưa có nguồn phù hợp" in result["output"].answer
    assert result["output"].sources == []
    assert "not configured" in result["output"].warnings[0]
