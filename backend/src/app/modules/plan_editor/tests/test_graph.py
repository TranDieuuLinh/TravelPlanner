import asyncio

from app.modules.plan_editor.public import build_plan_editor_graph
from app.shared.contracts.itinerary import Itinerary, ItineraryDay, ItineraryItem
from app.shared.contracts.place import Coordinates, VerifiedPlace
from app.shared.contracts.trip import TripIntent


def itinerary_fixture() -> Itinerary:
    place = VerifiedPlace(
        place_id="place-1",
        name="Place 1",
        coordinates=Coordinates(latitude=16, longitude=108),
        source="test",
    )
    return Itinerary(
        itinerary_id="itinerary-1",
        intent=TripIntent(destination="Đà Nẵng", days=1),
        days=[
            ItineraryDay(
                day=1,
                items=[
                    ItineraryItem(
                        item_id="item-1",
                        place=place,
                        start_minute=540,
                        end_minute=630,
                    )
                ],
            )
        ],
    )


def test_locks_an_item_and_increments_revision() -> None:
    graph = build_plan_editor_graph()

    result = asyncio.run(
        graph.ainvoke(
            {
                "itinerary": itinerary_fixture(),
                "operation": {"type": "lock_item", "item_id": "item-1"},
            }
        )
    )

    output = result["output"]
    assert output.changed is True
    assert output.itinerary.revision == 2
    assert output.itinerary.days[0].items[0].locked is True
