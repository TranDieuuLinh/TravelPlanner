import asyncio

from app.modules.explorer.public import ExplorerPlace, PlaceSource
from app.modules.place_checker.public import build_place_checker_graph


def test_consumes_explorer_handoff_and_fills_coverage() -> None:
    graph = build_place_checker_graph()
    result = asyncio.run(graph.ainvoke({
        "input_adm": "Đà Nẵng",
        "places": [ExplorerPlace(
            name="Bảo tàng Đà Nẵng",
            sourcePlaces=[PlaceSource(
                origin="input", evidenceType="raw_prompt", evidence="Bảo tàng Đà Nẵng"
            )],
        )],
        "days": 2,
    }))

    output = result["output"]
    assert output.coverage_status == "sufficient"
    assert output.places[0].name == "Bảo tàng Đà Nẵng"
    assert len(output.places) == 4
    assert output.warnings
