from datetime import datetime, time, timedelta

from app.modules.plans.domain.entities import (
    PlanItem,
    PlanTransportLeg,
)
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.local_time import (
    combine_routing_datetime,
    normalize_routing_datetime,
)
from app.modules.plans.schema import (
    CurrentLocationRouteCreate,
    DayDirectionsCreate,
    RouteDestination,
)


class CurrentLocationRouteService:
    """Builds an ephemeral route from the user's device to a plan stop."""

    def __init__(self, optimizer: GeographicRouteOptimizer) -> None:
        self.optimizer = optimizer

    def calculate(
        self,
        payload: CurrentLocationRouteCreate,
    ) -> PlanTransportLeg:
        origin = PlanItem(
            itemId="current-location",
            name="Vị trí của bạn",
            timeWindow="00:00-00:01",
            placeType="current_location",
            latitude=payload.origin.latitude,
            longitude=payload.origin.longitude,
        )
        destination = PlanItem(
            itemId=payload.destination.item_id,
            name=payload.destination.name,
            address=payload.destination.address,
            timeWindow="00:01-00:02",
            placeType="destination",
            latitude=payload.destination.latitude,
            longitude=payload.destination.longitude,
        )
        return self.optimizer.calculate_leg(
            origin,
            destination,
            departure_time=(
                normalize_routing_datetime(payload.departure_time)
                if payload.departure_time is not None
                else None
            ),
            preferred_modes=set(payload.preferred_modes),
            avoid_modes=set(payload.avoid_modes),
        )

    def calculate_day(
        self,
        payload: DayDirectionsCreate,
    ) -> list[PlanTransportLeg]:
        origin = PlanItem(
            itemId="current-location",
            name="Vị trí của bạn",
            timeWindow="00:00-00:01",
            placeType="current_location",
            latitude=payload.origin.latitude,
            longitude=payload.origin.longitude,
        )
        destinations = [
            self._destination_item(destination)
            for destination in payload.destinations
        ]
        legs: list[PlanTransportLeg] = []
        request_departure_time = (
            normalize_routing_datetime(payload.departure_time)
            if payload.departure_time is not None
            else None
        )
        rolling_departure_time = request_departure_time
        for leg_index, (leg_origin, destination) in enumerate(zip(
            [origin, *destinations[:-1]],
            destinations,
        )):
            departure_time = rolling_departure_time
            if leg_index > 0:
                departure_time = (
                    _scheduled_departure_time(
                        leg_origin,
                        reference=request_departure_time,
                    )
                    or rolling_departure_time
                )
            if payload.requested_mode in {"walk", "car"}:
                leg = self.optimizer.calculate_leg(
                    leg_origin,
                    destination,
                    departure_time=departure_time,
                    requested_mode=payload.requested_mode,
                )
            else:
                leg = self._navigation_leg(
                    leg_origin,
                    destination,
                    departure_time=departure_time,
                )
            legs.append(leg)
            if departure_time is not None:
                rolling_departure_time = departure_time + timedelta(
                    minutes=leg.estimated_duration_minutes
                )
        return legs

    def _navigation_leg(
        self,
        origin: PlanItem,
        destination: PlanItem,
        *,
        departure_time: datetime | None,
    ) -> PlanTransportLeg:
        # The optimizer compares walking and car routes. Public transit is
        # temporarily disabled, so this makes no OTP/bus request.
        return self.optimizer.calculate_leg(
            origin,
            destination,
            departure_time=departure_time,
        )

    @staticmethod
    def _destination_item(destination: RouteDestination) -> PlanItem:
        return PlanItem(
            itemId=destination.item_id,
            name=destination.name,
            address=destination.address,
            timeWindow=destination.time_window or "",
            placeType="destination",
            latitude=destination.latitude,
            longitude=destination.longitude,
        )


def _scheduled_departure_time(
    origin: PlanItem,
    *,
    reference: datetime | None,
) -> datetime | None:
    if reference is None:
        return None
    parts = origin.time_window.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        departure_clock = time.fromisoformat(parts[1].strip())
    except ValueError:
        return None
    return combine_routing_datetime(reference.date(), departure_clock)


__all__ = ["CurrentLocationRouteService"]
