from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.modules.plans.domain.entities import PlanItem, PlanTransportLeg


class GeographicRouteOptimizer:
    """Optimizes an open day route using coordinates until a route provider exists."""

    road_distance_factor = 1.25

    def optimize(
        self,
        items: list[PlanItem],
        *,
        start: tuple[float, float] | None = None,
    ) -> tuple[list[PlanItem], list[PlanTransportLeg]]:
        located_positions = [
            index
            for index, item in enumerate(items)
            if item.latitude is not None and item.longitude is not None
        ]
        if len(located_positions) < 2:
            return list(items), []

        located = [items[index] for index in located_positions]
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
        return optimized, self._build_legs(optimized_located)

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
            mode = "walk" if estimated_distance <= 1500 else "ride_hailing"
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
