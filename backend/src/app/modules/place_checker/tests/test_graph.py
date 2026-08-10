import asyncio

from app.modules.place_checker.public import build_place_checker_graph
from app.shared.contracts.place import Coordinates, PlaceCandidate
from app.shared.contracts.trip import TripIntent


def test_preserves_candidate_and_fills_coverage() -> None:
    graph = build_place_checker_graph()
    candidate = PlaceCandidate(
        name="Bảo tàng",
        coordinates=Coordinates(latitude=16.06, longitude=108.22),
    )

    result = asyncio.run(
        graph.ainvoke(
            {
                "intent": TripIntent(destination="Đà Nẵng", days=2),
                "candidates": [candidate],
            }
        )
    )

    output = result["output"]
    assert output.coverage_status == "sufficient"
    assert output.places[0].name == "Bảo tàng"
    assert len(output.places) == 4
    assert output.warnings
