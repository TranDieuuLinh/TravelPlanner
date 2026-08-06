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
    TravelTimeMatrixProvider,
)
from app.modules.plans.routing.local_time import (
    combine_routing_datetime,
    routing_today,
)


class RouteUnavailableError(ValueError):
    """Raised when an explicitly requested mode has no provider route."""


class GeographicRouteOptimizer:
    """Optimizes a day route and enriches each leg with provider routing."""

    road_distance_factor = 1.25
    max_walking_distance_meters = 1500
    walking_prefilter_distance_meters = 2000

    def __init__(
        self,
        route_provider: RouteProvider | None = None,
        transit_provider: TransitRouteProvider | None = None,
        matrix_provider: TravelTimeMatrixProvider | None = None,
    ) -> None:
        self.route_provider = route_provider
        self.transit_provider = transit_provider
        self.matrix_provider = matrix_provider

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
        reusable_legs: list[PlanTransportLeg] | None = None,
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
                reusable_legs=reusable_legs,
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

    def order_from_start(
        self,
        items: list[PlanItem],
        *,
        start: tuple[float, float],
        departure_time: datetime | None = None,
    ) -> list[PlanItem]:
        """Order navigation stops by provider travel time, with geo fallback."""
        if len(items) < 2:
            return list(items)
        if self.matrix_provider is not None:
            coordinates = [start, *(self._coordinate(item) for item in items)]
            matrix = self.matrix_provider.calculate(
                coordinates,
                transport_mode="car",
                departure_time=departure_time,
            )
            if matrix is not None:
                order = self._travel_time_order(
                    matrix.travel_times_seconds,
                    item_count=len(items),
                )
                if order is not None:
                    return [items[index] for index in order]
        if len(items) <= 10:
            order = self._shortest_open_path_order(items, start=start)
            return [items[index] for index in order]
        order = self._best_nearest_neighbour_order(items, start=start)
        order = self._two_opt(items, order, start=start)
        return [items[index] for index in order]

    def _travel_time_order(
        self,
        matrix: list[list[int | None]],
        *,
        item_count: int,
    ) -> list[int] | None:
        expected_size = item_count + 1
        if len(matrix) != expected_size or any(
            len(row) != expected_size for row in matrix
        ):
            return None
        if item_count <= 10:
            return self._exact_matrix_open_path(matrix, item_count=item_count)
        order = self._matrix_nearest_neighbour_order(
            matrix,
            item_count=item_count,
        )
        if order is None:
            return None
        return self._improve_matrix_order(matrix, order)

    @staticmethod
    def _exact_matrix_open_path(
        matrix: list[list[int | None]],
        *,
        item_count: int,
    ) -> list[int] | None:
        costs: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {}
        for item_index in range(item_count):
            travel_time = matrix[0][item_index + 1]
            if travel_time is not None:
                costs[(1 << item_index, item_index)] = (
                    travel_time,
                    (item_index,),
                )
        for mask in range(1, 1 << item_count):
            for last in range(item_count):
                state = costs.get((mask, last))
                if state is None:
                    continue
                cost, path = state
                for next_index in range(item_count):
                    if mask & (1 << next_index):
                        continue
                    travel_time = matrix[last + 1][next_index + 1]
                    if travel_time is None:
                        continue
                    next_mask = mask | (1 << next_index)
                    candidate = (
                        cost + travel_time,
                        (*path, next_index),
                    )
                    existing = costs.get((next_mask, next_index))
                    if existing is None or candidate < existing:
                        costs[(next_mask, next_index)] = candidate
        complete_mask = (1 << item_count) - 1
        complete = [
            costs[(complete_mask, last)]
            for last in range(item_count)
            if (complete_mask, last) in costs
        ]
        return list(min(complete)[1]) if complete else None

    @staticmethod
    def _matrix_nearest_neighbour_order(
        matrix: list[list[int | None]],
        *,
        item_count: int,
    ) -> list[int] | None:
        remaining = set(range(item_count))
        order: list[int] = []
        matrix_origin = 0
        while remaining:
            reachable = [
                index
                for index in remaining
                if matrix[matrix_origin][index + 1] is not None
            ]
            if not reachable:
                return None
            next_index = min(
                reachable,
                key=lambda index: (
                    matrix[matrix_origin][index + 1],
                    index,
                ),
            )
            order.append(next_index)
            remaining.remove(next_index)
            matrix_origin = next_index + 1
        return order

    def _improve_matrix_order(
        self,
        matrix: list[list[int | None]],
        order: list[int],
    ) -> list[int]:
        best = list(order)
        best_cost = self._matrix_path_cost(matrix, best)
        if best_cost is None:
            return best
        improved = True
        while improved:
            improved = False
            for start_index in range(len(best) - 1):
                for end_index in range(start_index + 1, len(best)):
                    candidate = [
                        *best[:start_index],
                        *reversed(best[start_index : end_index + 1]),
                        *best[end_index + 1 :],
                    ]
                    candidate_cost = self._matrix_path_cost(matrix, candidate)
                    if candidate_cost is not None and candidate_cost < best_cost:
                        best = candidate
                        best_cost = candidate_cost
                        improved = True
        return best

    @staticmethod
    def _matrix_path_cost(
        matrix: list[list[int | None]],
        order: list[int],
    ) -> int | None:
        total = 0
        matrix_origin = 0
        for item_index in order:
            travel_time = matrix[matrix_origin][item_index + 1]
            if travel_time is None:
                return None
            total += travel_time
            matrix_origin = item_index + 1
        return total

    def _shortest_open_path_order(
        self,
        items: list[PlanItem],
        *,
        start: tuple[float, float],
    ) -> list[int]:
        """Solve the exact start-to-all-stops path without returning home."""
        coordinates = [self._coordinate(item) for item in items]
        size = len(coordinates)
        costs: dict[tuple[int, int], tuple[float, tuple[int, ...]]] = {
            (1 << index, index): (
                _haversine_meters(start, coordinate),
                (index,),
            )
            for index, coordinate in enumerate(coordinates)
        }
        for mask in range(1, 1 << size):
            for last in range(size):
                state = costs.get((mask, last))
                if state is None:
                    continue
                cost, path = state
                for next_index in range(size):
                    if mask & (1 << next_index):
                        continue
                    next_mask = mask | (1 << next_index)
                    next_cost = cost + _haversine_meters(
                        coordinates[last],
                        coordinates[next_index],
                    )
                    existing = costs.get((next_mask, next_index))
                    candidate = (next_cost, (*path, next_index))
                    if existing is None or candidate < existing:
                        costs[(next_mask, next_index)] = candidate
        complete_mask = (1 << size) - 1
        return list(min(costs[(complete_mask, last)] for last in range(size))[1])

    def calculate_leg(
        self,
        origin: PlanItem,
        destination: PlanItem,
        *,
        departure_time: datetime | None = None,
        preferred_modes: set[str] | None = None,
        avoid_modes: set[str] | None = None,
        requested_mode: str | None = None,
    ) -> PlanTransportLeg:
        """Calculate one route without adding the live origin to a saved plan."""
        origin_coordinate = self._coordinate(origin)
        destination_coordinate = self._coordinate(destination)
        if requested_mode is not None:
            provider_route, mode = self._requested_provider_route(
                origin_coordinate,
                destination_coordinate,
                departure_time=departure_time,
                requested_mode=requested_mode,
            )
            if requested_mode.casefold() == "bus" and provider_route is None:
                raise RouteUnavailableError(
                    "Không có tuyến phương tiện công cộng cho chặng này."
                )
            alternatives: list[PlanTransportOption] = []
        else:
            provider_route, mode, alternatives = self._best_provider_route(
                origin_coordinate,
                destination_coordinate,
                departure_time=departure_time,
                preferred_modes=preferred_modes or set(),
                avoid_modes=avoid_modes or set(),
            )
        return self._route_or_fallback_leg(
            origin,
            destination,
            provider_route=provider_route,
            mode=mode,
            alternatives=alternatives,
            requested_mode=requested_mode,
        )

    def _route_or_fallback_leg(
        self,
        origin: PlanItem,
        destination: PlanItem,
        *,
        provider_route: RouteCalculation | None,
        mode: str,
        alternatives: list[PlanTransportOption],
        requested_mode: str | None = None,
    ) -> PlanTransportLeg:
        if provider_route is not None:
            return self._provider_leg(
                origin,
                destination,
                provider_route,
                mode=mode,
                alternatives=alternatives,
            )

        origin_coordinate = self._coordinate(origin)
        destination_coordinate = self._coordinate(destination)
        straight_distance = _haversine_meters(
            origin_coordinate,
            destination_coordinate,
        )
        estimated_distance = int(round(straight_distance * self.road_distance_factor))
        fallback_mode = _fallback_mode(
            requested_mode,
            distance_meters=estimated_distance,
            walking_threshold=self.max_walking_distance_meters,
        )
        speed_kmh = {
            "walk": 4.5,
            "car": 22.0,
            "public_transit": 18.0,
            "ride_hailing": 22.0,
        }[fallback_mode]
        duration = max(
            1,
            int(round(estimated_distance / 1000 / speed_kmh * 60)),
        )
        return PlanTransportLeg(
            fromItemId=origin.item_id,
            toItemId=destination.item_id,
            fromPlace=origin.name,
            toPlace=destination.name,
            mode=fallback_mode,
            distanceMeters=estimated_distance,
            estimatedDurationMinutes=duration,
            geometryCoordinates=[
                origin_coordinate,
                destination_coordinate,
            ],
            source="geodesic_estimate",
            verified=False,
        )

    def _requested_provider_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        departure_time: datetime | None,
        requested_mode: str,
    ) -> tuple[RouteCalculation | None, str]:
        normalized = requested_mode.casefold()
        if normalized == "walk":
            route = (
                self.route_provider.calculate(
                    origin,
                    destination,
                    transport_mode="pedestrian",
                    departure_time=departure_time,
                )
                if self.route_provider is not None
                else None
            )
            return route, "walk"
        if normalized == "car":
            route = (
                self.route_provider.calculate(
                    origin,
                    destination,
                    transport_mode="car",
                    departure_time=departure_time,
                )
                if self.route_provider is not None
                else None
            )
            return route, "car"
        if normalized == "bus":
            route = (
                self.transit_provider.calculate(
                    origin,
                    destination,
                    departure_time=departure_time,
                    modes=("bus",),
                )
                if self.transit_provider is not None
                else None
            )
            return route, "public_transit"
        raise ValueError(f"Unsupported requested route mode: {requested_mode}")

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
        reusable_legs: list[PlanTransportLeg] | None = None,
    ) -> list[PlanTransportLeg]:
        reusable_by_pair = {
            (leg.from_item_id, leg.to_item_id): leg
            for leg in reusable_legs or []
            if leg.from_item_id and leg.to_item_id
        }
        batched_road_routes = self._batch_road_routes(
            items,
            day=day,
            trip_start_date=trip_start_date,
            preferred_modes=preferred_modes,
            avoid_modes=avoid_modes,
        )
        if batched_road_routes is not None:
            walking_routes, car_routes = batched_road_routes
            return self._build_legs_from_batched_roads(
                items,
                walking_routes=walking_routes,
                car_routes=car_routes,
                day=day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
                reusable_by_pair=reusable_by_pair,
            )

        legs: list[PlanTransportLeg] = []
        for origin, destination in zip(items, items[1:]):
            reusable = reusable_by_pair.get((origin.item_id, destination.item_id))
            if (
                reusable is not None
                and reusable.from_place == origin.name
                and reusable.to_place == destination.name
            ):
                legs.append(reusable)
                continue
            legs.append(
                self.calculate_leg(
                    origin,
                    destination,
                    departure_time=_leg_departure_time(
                        origin,
                        day=day,
                        trip_start_date=trip_start_date,
                    ),
                    preferred_modes=preferred_modes,
                    avoid_modes=avoid_modes,
                )
            )
        return legs

    def _batch_road_routes(
        self,
        items: list[PlanItem],
        *,
        day: int,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> (
        tuple[
            list[RouteCalculation | None],
            list[RouteCalculation | None],
        ]
        | None
    ):
        calculate_many = getattr(self.route_provider, "calculate_many", None)
        if not callable(calculate_many) or len(items) < 2:
            return None

        coordinates = [self._coordinate(item) for item in items]
        leg_count = len(items) - 1
        normalized_preferred = {mode.casefold() for mode in preferred_modes}
        normalized_avoid = {mode.casefold() for mode in avoid_modes}
        avoid_walk = "walk" in normalized_avoid
        avoid_car = bool(
            normalized_avoid & {"car", "private_car", "taxi", "ride_hailing"}
        )
        prefer_car = bool(
            normalized_preferred & {"car", "private_car", "taxi", "ride_hailing"}
        )
        departure_time = _leg_departure_time(
            items[0],
            day=day,
            trip_start_date=trip_start_date,
        )
        walk_eligible = [
            _haversine_meters(origin, destination)
            <= self.walking_prefilter_distance_meters
            for origin, destination in zip(coordinates, coordinates[1:])
        ]
        walking_routes: list[RouteCalculation | None] = [None] * leg_count
        if not avoid_walk and not prefer_car and any(walk_eligible):
            batch = calculate_many(
                coordinates,
                transport_mode="pedestrian",
                departure_time=departure_time,
            )
            if batch is not None and len(batch) == leg_count:
                walking_routes = [
                    route if eligible else None
                    for route, eligible in zip(batch, walk_eligible)
                ]

        needs_car = prefer_car or any(
            route is None or route.distance_meters > self.max_walking_distance_meters
            for route in walking_routes
        )
        car_routes: list[RouteCalculation | None] = [None] * leg_count
        if not avoid_car and needs_car:
            batch = calculate_many(
                coordinates,
                transport_mode="car",
                departure_time=departure_time,
            )
            if batch is not None and len(batch) == leg_count:
                car_routes = list(batch)
        return walking_routes, car_routes

    def _build_legs_from_batched_roads(
        self,
        items: list[PlanItem],
        *,
        walking_routes: list[RouteCalculation | None],
        car_routes: list[RouteCalculation | None],
        day: int,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
        reusable_by_pair: dict[tuple[str | None, str | None], PlanTransportLeg],
    ) -> list[PlanTransportLeg]:
        normalized_preferred = {mode.casefold() for mode in preferred_modes}
        normalized_avoid = {mode.casefold() for mode in avoid_modes}
        avoid_walk = "walk" in normalized_avoid
        prefer_transit = bool(
            normalized_preferred & {"bus", "train", "public_transit", "transit"}
        )
        avoid_car = bool(
            normalized_avoid & {"car", "private_car", "taxi", "ride_hailing"}
        )
        avoid_transit = bool(normalized_avoid & {"public_transit", "transit"}) or {
            "bus",
            "train",
        }.issubset(normalized_avoid)

        legs: list[PlanTransportLeg] = []
        for index, (origin, destination) in enumerate(zip(items, items[1:])):
            reusable = reusable_by_pair.get((origin.item_id, destination.item_id))
            if (
                reusable is not None
                and reusable.from_place == origin.name
                and reusable.to_place == destination.name
            ):
                legs.append(reusable)
                continue

            walking_route = walking_routes[index]
            car_route = car_routes[index]
            transit_route = None
            walking_is_practical = bool(
                walking_route is not None
                and walking_route.distance_meters <= self.max_walking_distance_meters
            )
            should_query_transit = (
                prefer_transit
                or (avoid_car and not walking_is_practical)
                or (walking_route is None and car_route is None)
            )
            if (
                should_query_transit
                and self.transit_provider is not None
                and not avoid_transit
            ):
                transit_route = self.transit_provider.calculate(
                    self._coordinate(origin),
                    self._coordinate(destination),
                    departure_time=_leg_departure_time(
                        origin,
                        day=day,
                        trip_start_date=trip_start_date,
                    ),
                    modes=_transit_mode_filter(
                        normalized_preferred,
                        normalized_avoid,
                    ),
                )

            selection_preferred_modes = preferred_modes
            if avoid_car and not walking_is_practical and transit_route is not None:
                selection_preferred_modes = {
                    *preferred_modes,
                    "public_transit",
                }
            provider_route, mode, alternatives = self._select_best_provider_route(
                walking_route,
                car_route,
                transit_route,
                preferred_modes=selection_preferred_modes,
                avoid_modes=avoid_modes,
            )
            fallback_requested_mode = (
                "walk"
                if avoid_car and not avoid_walk
                else "car" if avoid_walk and not avoid_car else None
            )
            legs.append(
                self._route_or_fallback_leg(
                    origin,
                    destination,
                    provider_route=provider_route,
                    mode=mode,
                    alternatives=alternatives,
                    requested_mode=fallback_requested_mode,
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
        normalized_preferred = {mode.casefold() for mode in preferred_modes}
        normalized_avoid = {mode.casefold() for mode in avoid_modes}
        avoid_walk = "walk" in normalized_avoid
        avoid_car = bool(
            normalized_avoid & {"car", "private_car", "taxi", "ride_hailing"}
        )
        avoid_transit = bool(normalized_avoid & {"public_transit", "transit"}) or {
            "bus",
            "train",
        }.issubset(normalized_avoid)
        walking_route = (
            self.route_provider.calculate(
                origin,
                destination,
                transport_mode="pedestrian",
                departure_time=departure_time,
            )
            if self.route_provider is not None and not avoid_walk
            else None
        )
        car_route = (
            self.route_provider.calculate(
                origin,
                destination,
                transport_mode="car",
                departure_time=departure_time,
            )
            if self.route_provider is not None and not avoid_car
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
            if self.transit_provider is not None and not avoid_transit
            else None
        )

        return self._select_best_provider_route(
            walking_route,
            car_route,
            transit_route,
            preferred_modes=preferred_modes,
            avoid_modes=avoid_modes,
        )

    def _select_best_provider_route(
        self,
        walking_route: RouteCalculation | None,
        car_route: RouteCalculation | None,
        transit_route: RouteCalculation | None,
        *,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> tuple[
        RouteCalculation | None,
        str,
        list[PlanTransportOption],
    ]:
        normalized_preferred = {mode.casefold() for mode in preferred_modes}
        prefer_car = bool(
            normalized_preferred & {"car", "private_car", "taxi", "ride_hailing"}
        )
        prefer_transit = bool(
            normalized_preferred & {"bus", "train", "public_transit", "transit"}
        )

        road_choices: list[tuple[RouteCalculation, str]] = []
        if walking_route is not None:
            road_choices.append((walking_route, "walk"))
        if car_route is not None:
            road_choices.append((car_route, "ride_hailing"))

        road_route: RouteCalculation | None = None
        road_mode = ""
        if (
            walking_route is not None
            and walking_route.distance_meters <= self.max_walking_distance_meters
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
            alternatives = [
                self._provider_option(route, mode=mode) for route, mode in road_choices
            ]
            return transit_route, "public_transit", alternatives

        alternatives = [
            self._provider_option(route, mode=mode)
            for route, mode in road_choices
            if mode != road_mode
        ]
        if transit_route is not None:
            alternatives.append(
                self._provider_option(
                    transit_route,
                    mode="public_transit",
                )
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
        normalized_alternatives = [
            option.model_copy(
                update={
                    "details": _with_route_endpoints(
                        option.details,
                        from_place=origin.name,
                        to_place=destination.name,
                    )
                }
            )
            for option in alternatives
        ]
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
            verified=_route_is_current(route),
            fetchedAt=route.fetched_at,
            details=_with_route_endpoints(
                route.details,
                from_place=origin.name,
                to_place=destination.name,
            ),
            alternatives=normalized_alternatives,
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
            verified=_route_is_current(route),
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


def _route_is_current(route: RouteCalculation) -> bool:
    return route.details.get("scheduleStatus", "current") == "current"


def _with_route_endpoints(
    details: dict,
    *,
    from_place: str,
    to_place: str,
) -> dict:
    raw_segments = details.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        return details
    segments = [
        dict(segment) if isinstance(segment, dict) else {} for segment in raw_segments
    ]
    segments[0]["fromPlace"] = from_place
    segments[-1]["toPlace"] = to_place
    return {**details, "segments": segments}


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
        + cos(latitude_1) * cos(latitude_2) * sin(delta_longitude / 2) ** 2
    )
    return 6_371_000 * 2 * asin(sqrt(value))


def _leg_departure_time(
    origin: PlanItem,
    *,
    day: int,
    trip_start_date: str | None,
) -> datetime | None:
    if trip_start_date is None:
        departure_date = routing_today()
    else:
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
    return combine_routing_datetime(departure_date, departure_clock)


def _transit_mode_filter(
    preferred_modes: set[str],
    avoid_modes: set[str],
) -> tuple[str, ...]:
    included: list[str] = []
    if "bus" in preferred_modes and "bus" not in avoid_modes:
        included.append("bus")
    if "train" in preferred_modes and "train" not in avoid_modes:
        included.append("train")
    if included:
        return tuple(included)

    excluded: list[str] = []
    if "bus" in avoid_modes:
        excluded.append("-bus")
    if "train" in avoid_modes:
        excluded.append("-train")
    return tuple(excluded)


def _fallback_mode(
    requested_mode: str | None,
    *,
    distance_meters: int,
    walking_threshold: int,
) -> str:
    normalized = requested_mode.casefold() if requested_mode else ""
    if normalized == "walk":
        return "walk"
    if normalized == "car":
        return "car"
    if normalized == "bus":
        return "public_transit"
    return "walk" if distance_meters <= walking_threshold else "ride_hailing"
