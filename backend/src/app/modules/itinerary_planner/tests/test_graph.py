import asyncio

from app.modules.itinerary_planner.public import build_itinerary_planner_graph
from app.shared.contracts.place import Coordinates, VerifiedPlace
from app.shared.contracts.trip import TripIntent


def test_allocates_places_across_requested_days() -> None:
    graph = build_itinerary_planner_graph()
    places = [
        VerifiedPlace(
            place_id=f"place-{index}",
            name=f"Place {index}",
            coordinates=Coordinates(latitude=16 + index / 100, longitude=108),
            source="test",
        )
        for index in range(4)
    ]

    result = asyncio.run(
        graph.ainvoke(
            {"intent": TripIntent(destination="Đà Nẵng", days=2), "places": places}
        )
    )

    itinerary = result["output"].itinerary
    assert len(itinerary.days) == 2
    assert [len(day.items) for day in itinerary.days] == [2, 2]
