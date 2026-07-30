from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import asin, ceil, cos, radians, sin, sqrt

from app.modules.plans.domain.entities import (
    PlanItem,
    PlanTransportLeg,
    PlanTransportOption,
)
from app.modules.plans.routing.provider import (
    RouteCalculation,
    RouteProvider,
    TransitRouteProvider,
)


class GeographicRouteOptimizer:
    """Optimizes a day route and enriches each leg with provider routing."""

    road_distance_factor = 1.25
    max_walking_distance_meters = 1500

    def __init__(
        self,
        route_provider: RouteProvider | None = None,
        transit_provider: TransitRouteProvider | None = None,
    ) -> None:
        self.route_provider = route_provider
        self.transit_provider = transit_provider

    def optimize(
        self,
        items: list[PlanItem],
        *,
        start: tuple[float, float] | None = None,
        preserve_order: bool = False,
        day: int = 1,
        trip_start_date: str | None = None,
        preferred_modes: set[str] | None = None,
        avoid_modes: set[str] | None = None,
    ) -> tuple[list[PlanItem], list[PlanTransportLeg]]:
        located_positions = [
            index
            for index, item in enumerate(items)
            if item.latitude is not None and item.longitude is not None
        ]
        if len(located_positions) < 2:
            return list(items), []

        located = [items[index] for index in located_positions]
        if preserve_order:
            return list(items), self._build_legs(
                located,
                day=day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes or set(),
                avoid_modes=avoid_modes or set(),
            )
        order = self._best_nearest_neighbour_order(located, start=start)
        order = self._two_opt(located, order, start=start)
        ordered_items = [located[index] for index in order]

        optimized = list(items)
        for position, selected in zip(located_positions, ordered_items):
            slot = items[position]
            optimized[position] = selected.model_copy(
                update={
                    "time_window": slot.time_window,
                    "role": slot.role,
                }
            )
        optimized_located = [optimized[index] for index in located_positions]
        return optimized, self._build_legs(
            optimized_located,
            day=day,
            trip_start_date=trip_start_date,
            preferred_modes=preferred_modes or set(),
            avoid_modes=avoid_modes or set(),
        )

    def _best_nearest_neighbour_order(
        self,
        items: list[PlanItem],
        *,
        start: tuple[float, float] | None,
    ) -> list[int]:
        starts = [None] if start is not None else list(range(len(items)))
        best_order: list[int] | None = None
        best_cost = float("inf")
        for first in starts:
            remaining = set(range(len(items)))
            order: list[int] = []
            current_coordinate = start
            if first is not None:
                order.append(first)
                remaining.remove(first)
                current_coordinate = self._coordinate(items[first])
            while remaining:
                next_index = min(
                    remaining,
                    key=lambda index: self._distance_from(
                        current_coordinate,
                        self._coordinate(items[index]),
                    ),
                )
                order.append(next_index)
                remaining.remove(next_index)
                current_coordinate = self._coordinate(items[next_index])
            cost = self._route_cost(items, order, start=start)
            if cost < best_cost:
                best_cost = cost
                best_order = order
        return best_order or list(range(len(items)))

    def _two_opt(
        self,
        items: list[PlanItem],
        order: list[int],
        *,
        start: tuple[float, float] | None,
    ) -> list[int]:
        best = list(order)
        best_cost = self._route_cost(items, best, start=start)
        improved = True
        while improved:
            improved = False
            for left in range(0, len(best) - 1):
                for right in range(left + 1, len(best)):
                    candidate = [
                        *best[:left],
                        *reversed(best[left : right + 1]),
                        *best[right + 1 :],
                    ]
                    cost = self._route_cost(items, candidate, start=start)
                    if cost + 0.001 < best_cost:
                        best = candidate
                        best_cost = cost
                        improved = True
            order = best
        return best

    def _route_cost(
        self,
        items: list[PlanItem],
        order: list[int],
        *,
        start: tuple[float, float] | None,
    ) -> float:
        coordinates = [self._coordinate(items[index]) for index in order]
        cost = 0.0
        if start is not None and coordinates:
            cost += _haversine_meters(start, coordinates[0])
        cost += sum(
            _haversine_meters(origin, destination)
            for origin, destination in zip(coordinates, coordinates[1:])
        )
        return cost

    def _build_legs(
        self,
        items: list[PlanItem],
        *,
        day: int,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> list[PlanTransportLeg]:
        legs: list[PlanTransportLeg] = []
        for origin, destination in zip(items, items[1:]):
            origin_coordinate = self._coordinate(origin)
            destination_coordinate = self._coordinate(destination)
            straight_distance = _haversine_meters(
                origin_coordinate,
                destination_coordinate,
            )
            estimated_distance = int(
                round(straight_distance * self.road_distance_factor)
            )
            provider_route, mode, alternatives = self._best_provider_route(
                origin_coordinate,
                destination_coordinate,
                departure_time=_leg_departure_time(
                    origin,
                    day=day,
                    trip_start_date=trip_start_date,
                ),
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
            )
            if provider_route is not None:
                legs.append(
                    self._provider_leg(
                        origin,
                        destination,
                        provider_route,
                        mode=mode,
                        alternatives=alternatives,
                    )
                )
                continue
            mode = (
                "walk"
                if estimated_distance <= self.max_walking_distance_meters
                else "ride_hailing"
            )
            speed_kmh = 4.5 if mode == "walk" else 22.0
            duration = max(
                1,
                int(round(estimated_distance / 1000 / speed_kmh * 60)),
            )
            legs.append(
                PlanTransportLeg(
                    fromItemId=origin.item_id,
                    toItemId=destination.item_id,
                    fromPlace=origin.name,
                    toPlace=destination.name,
                    mode=mode,
                    distanceMeters=estimated_distance,
                    estimatedDurationMinutes=duration,
                    geometryCoordinates=[
                        origin_coordinate,
                        destination_coordinate,
                    ],
                    source="geodesic_estimate",
                    verified=False,
                )
            )
        return legs

    def _best_provider_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        departure_time: datetime | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> tuple[
        RouteCalculation | None,
        str,
        list[PlanTransportOption],
    ]:
        normalized_preferred = {
            mode.casefold() for mode in preferred_modes
        }
        normalized_avoid = {mode.casefold() for mode in avoid_modes}
        avoid_walk = "walk" in normalized_avoid
        avoid_car = bool(
            normalized_avoid
            & {"car", "private_car", "taxi", "ride_hailing"}
        )
        avoid_transit = bool(
            normalized_avoid & {"public_transit", "transit"}
        ) or {"bus", "train"}.issubset(normalized_avoid)
        prefer_car = bool(
            normalized_preferred
            & {"car", "private_car", "taxi", "ride_hailing"}
        )
        prefer_transit = bool(
            normalized_preferred
            & {"bus", "train", "public_transit", "transit"}
        )

        walking_route = (
            self.route_provider.calculate(
                origin,
                destination,
                transport_mode="pedestrian",
            )
            if self.route_provider is not None and not avoid_walk
            else None
        )
        car_route = (
            self.route_provider.calculate(
                origin,
                destination,
                transport_mode="car",
            )
            if self.route_provider is not None
            and not avoid_car
            and (
                walking_route is None
                or walking_route.distance_meters
                > self.max_walking_distance_meters
                or prefer_car
                or prefer_transit
            )
            else None
        )
        transit_route = (
            self.transit_provider.calculate(
                origin,
                destination,
                departure_time=departure_time,
                modes=_transit_mode_filter(
                    normalized_preferred,
                    normalized_avoid,
                ),
            )
            if self.transit_provider is not None
            and not avoid_transit
            else None
        )

        road_route: RouteCalculation | None = None
        road_mode = ""
        if (
            walking_route is not None
            and walking_route.distance_meters
            <= self.max_walking_distance_meters
            and not prefer_car
        ):
            road_route = walking_route
            road_mode = "walk"
        elif car_route is not None:
            road_route = car_route
            road_mode = "ride_hailing"
        elif walking_route is not None:
            road_route = walking_route
            road_mode = "walk"

        if transit_route is not None and (prefer_transit or road_route is None):
            alternatives = (
                [self._provider_option(road_route, mode=road_mode)]
                if road_route is not None
                else []
            )
            return transit_route, "public_transit", alternatives

        alternatives = (
            [self._provider_option(transit_route, mode="public_transit")]
            if transit_route is not None
            else []
        )
        if road_route is not None:
            return road_route, road_mode, alternatives
        return None, "", alternatives

    def _provider_leg(
        self,
        origin: PlanItem,
        destination: PlanItem,
        route: RouteCalculation,
        *,
        mode: str,
        alternatives: list[PlanTransportOption],
    ) -> PlanTransportLeg:
        return PlanTransportLeg(
            fromItemId=origin.item_id,
            toItemId=destination.item_id,
            fromPlace=origin.name,
            toPlace=destination.name,
            mode=mode,
            distanceMeters=route.distance_meters,
            estimatedDurationMinutes=max(
                1,
                ceil(route.duration_seconds / 60),
            ),
            geometryCoordinates=route.geometry_coordinates,
            source=route.provider,
            verified=True,
            fetchedAt=route.fetched_at,
            details=route.details,
            alternatives=alternatives,
        )

    def _provider_option(
        self,
        route: RouteCalculation,
        *,
        mode: str,
    ) -> PlanTransportOption:
        return PlanTransportOption(
            mode=mode,
            distanceMeters=route.distance_meters,
            estimatedDurationMinutes=max(
                1,
                ceil(route.duration_seconds / 60),
            ),
            geometryCoordinates=route.geometry_coordinates,
            source=route.provider,
            verified=True,
            fetchedAt=route.fetched_at,
            details=route.details,
        )

    def _coordinate(self, item: PlanItem) -> tuple[float, float]:
        assert item.latitude is not None
        assert item.longitude is not None
        return item.latitude, item.longitude

    def _distance_from(
        self,
        origin: tuple[float, float] | None,
        destination: tuple[float, float],
    ) -> float:
        if origin is None:
            return 0.0
        return _haversine_meters(origin, destination)


def _haversine_meters(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> float:
    latitude_1, longitude_1 = map(radians, origin)
    latitude_2, longitude_2 = map(radians, destination)
    delta_latitude = latitude_2 - latitude_1
    delta_longitude = longitude_2 - longitude_1
    value = (
        sin(delta_latitude / 2) ** 2
        + cos(latitude_1)
        * cos(latitude_2)
        * sin(delta_longitude / 2) ** 2
    )
    return 6_371_000 * 2 * asin(sqrt(value))


def _leg_departure_time(
    origin: PlanItem,
    *,
    day: int,
    trip_start_date: str | None,
) -> datetime | None:
    if trip_start_date is None:
        return None
    try:
        departure_date = date.fromisoformat(trip_start_date) + timedelta(
            days=day - 1
        )
    except ValueError:
        return None
    parts = origin.time_window.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        departure_clock = time.fromisoformat(parts[1].strip())
    except ValueError:
        return None
    return datetime.combine(departure_date, departure_clock)


def _transit_mode_filter(
    preferred_modes: set[str],
    avoid_modes: set[str],
) -> tuple[str, ...]:
    train_modes = (
        "highSpeedTrain",
        "intercityTrain",
        "interRegionalTrain",
        "regionalTrain",
        "cityTrain",
        "subway",
        "lightRail",
        "monorail",
    )
    included: list[str] = []
    if "bus" in preferred_modes and "bus" not in avoid_modes:
        included.append("bus")
    if "train" in preferred_modes and "train" not in avoid_modes:
        included.extend(train_modes)
    if included:
        return tuple(included)

    excluded: list[str] = []
    if "bus" in avoid_modes:
        excluded.append("-bus")
    if "train" in avoid_modes:
        excluded.extend(f"-{mode}" for mode in train_modes)
    return tuple(excluded)
