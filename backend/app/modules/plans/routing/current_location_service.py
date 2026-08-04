from datetime import datetime, time, timedelta

from app.modules.plans.domain.entities import (
    PlanItem,
    PlanTransportLeg,
    PlanTransportOption,
)
from app.modules.plans.routing.optimizer import (
    GeographicRouteOptimizer,
    RouteUnavailableError,
)
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
            name=payload.origin.name or "Vị trí của bạn",
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
            name=payload.origin.name or "Vị trí của bạn",
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
            if payload.requested_mode is not None:
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
        choices: list[PlanTransportLeg] = []
        for mode in ("walk", "car", "bus"):
            try:
                choice = self.optimizer.calculate_leg(
                    origin,
                    destination,
                    departure_time=departure_time,
                    requested_mode=mode,
                )
            except RouteUnavailableError:
                continue
            choices.append(choice)
        recommended = _recommended_navigation_choice(
            choices,
            walking_threshold=self.optimizer.max_walking_distance_meters,
        )
        if recommended is None:
            return self.optimizer.calculate_leg(
                origin,
                destination,
                departure_time=departure_time,
            )
        preferred = _navigation_mode(recommended.mode)

        alternatives = [
            _as_option(choice)
            for choice in choices
            if _navigation_mode(choice.mode) != preferred
        ]
        return recommended.model_copy(
            update={"alternatives": alternatives}
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
    return combine_routing_datetime(
        reference.date(),
        departure_clock,
    )


def _navigation_mode(mode: str | None) -> str | None:
    normalized = (mode or "").casefold()
    if "walk" in normalized:
        return "walk"
    if normalized in {"car", "private_car"} or any(
        token in normalized for token in ("ride", "hailing", "taxi")
    ):
        return "car"
    if any(
        token in normalized
        for token in ("bus", "public", "transit", "train")
    ):
        return "bus"
    return None


def _recommended_navigation_choice(
    choices: list[PlanTransportLeg],
    *,
    walking_threshold: int,
) -> PlanTransportLeg | None:
    by_mode = {
        _navigation_mode(choice.mode): choice
        for choice in choices
    }
    walking = by_mode.get("walk")
    car = by_mode.get("car")
    bus = by_mode.get("bus")
    if (
        walking is not None
        and walking.distance_meters <= walking_threshold
    ):
        return walking
    return car or walking or bus


def _as_option(leg: PlanTransportLeg) -> PlanTransportOption:
    return PlanTransportOption(
        mode=leg.mode,
        distanceMeters=leg.distance_meters,
        estimatedDurationMinutes=leg.estimated_duration_minutes,
        geometryCoordinates=leg.geometry_coordinates,
        source=leg.source,
        verified=leg.verified,
        fetchedAt=leg.fetched_at,
        details=leg.details,
    )
