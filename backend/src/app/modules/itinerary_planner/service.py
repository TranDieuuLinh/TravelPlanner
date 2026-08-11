from uuid import uuid4

from app.modules.itinerary_planner.contract import (
    ItineraryPlannerInput,
    ItineraryPlannerOutput,
)
from app.modules.itinerary_planner.ports import RoutingProvider
from app.shared.contracts.itinerary import Itinerary, ItineraryDay, ItineraryItem


class ItineraryPlannerService:
    def __init__(self, routing: RoutingProvider) -> None:
        self.routing = routing

    async def plan(self, payload: ItineraryPlannerInput) -> ItineraryPlannerOutput:
        day_places = [[] for _ in range(payload.intent.days)]
        for index, place in enumerate(payload.places):
            day_places[index % payload.intent.days].append(place)

        days: list[ItineraryDay] = []
        warnings = list(payload.upstream_warnings)
        for day_number, places in enumerate(day_places, start=1):
            cursor = 9 * 60
            items: list[ItineraryItem] = []
            previous = None
            for place in places:
                travel_minutes = (
                    await self.routing.travel_minutes(previous, place)
                    if previous is not None
                    else 0
                )
                start = cursor + travel_minutes
                end = min(start + place.estimated_visit_minutes, 21 * 60)
                if end <= start:
                    warnings.append(
                        f"{place.name} could not fit into day {day_number}."
                    )
                    continue
                items.append(
                    ItineraryItem(
                        item_id=str(uuid4()),
                        place=place,
                        start_minute=start,
                        end_minute=end,
                        travel_minutes_from_previous=travel_minutes,
                    )
                )
                cursor = end
                previous = place
            days.append(ItineraryDay(day=day_number, items=items))

        if not payload.places:
            warnings.append("No places were available for itinerary generation.")
        itinerary = Itinerary(
            itinerary_id=str(uuid4()),
            intent=payload.intent,
            days=days,
            total_estimated_cost=sum(
                place.estimated_cost * payload.intent.people for place in payload.places
            ),
            warnings=warnings,
        )
        return ItineraryPlannerOutput(itinerary=itinerary)
