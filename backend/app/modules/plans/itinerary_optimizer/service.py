from __future__ import annotations

import logging
from datetime import datetime, timedelta
from itertools import permutations
from math import asin, cos, radians, sin, sqrt
from typing import Protocol

from app.modules.plans.domain.entities import PlanDay, PlanItem, PlanTransportLeg
from app.modules.plans.routing.optimizer import GeographicRouteOptimizer
from app.modules.plans.routing.provider import TravelTimeMatrixProvider
from app.modules.plans.place_selector.timeline_policy import DAILY_ACTIVITY_MINUTES
from app.modules.plans.place_selector.time_windows import (
    parse_clock_minutes,
    time_window_matches_preference,
)
from app.modules.plans.trip_theme_planner.opening_hours_parser import (
    extract_time_intervals,
    is_24_hours,
)


logger = logging.getLogger(__name__)
PREFERRED_TIME_WINDOW_MISS_PENALTY_SECONDS = 90 * 60


class ItineraryOptimizer(Protocol):
    """Application boundary used by PlaceSelector to optimize one completed day."""

    supports_fixed_anchors: bool

    def optimize_trip(
        self,
        days: list[PlanDay],
        *,
        trip_start_date: str | None = None,
        preferred_modes: set[str] | None = None,
        avoid_modes: set[str] | None = None,
        enrich_routes: bool = True,
    ) -> list[PlanDay]: ...

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
    ) -> tuple[list[PlanItem], list[PlanTransportLeg]]: ...


class RouteFirstItineraryOptimizer:
    """Optimize activity order while keeping fixed timeline anchors in place.

    PlaceSelector assigns semantic roles and time slots before this boundary. This
    optimizer treats food/break blocks as fixed anchors, assigns activity
    Places to the remaining activity slots, and minimizes provider-backed
    travel time across the resulting day. Source itineraries can still request
    strict order preservation.
    """

    supports_fixed_anchors = True
    max_exact_activities = 8

    def __init__(
        self,
        legacy_optimizer: GeographicRouteOptimizer,
        matrix_provider: TravelTimeMatrixProvider | None = None,
    ) -> None:
        self.legacy_optimizer = legacy_optimizer
        self.matrix_provider = matrix_provider or legacy_optimizer.matrix_provider

    def optimize_trip(
        self,
        days: list[PlanDay],
        *,
        trip_start_date: str | None = None,
        preferred_modes: set[str] | None = None,
        avoid_modes: set[str] | None = None,
        enrich_routes: bool = True,
    ) -> list[PlanDay]:
        """Reassign movable activities across days before optimizing each day.

        Day themes are deliberately absent from the objective. They remain
        presentation/planning hints, while hard source-day provenance stays
        fixed. A deterministic pair-swap search reduces travel and balances
        activity minutes before each day receives its detailed meal-anchored
        timeline.
        """

        if len(days) < 2:
            return [
                self._optimize_plan_day(
                    day,
                    trip_start_date=trip_start_date,
                    preferred_modes=preferred_modes or set(),
                    avoid_modes=avoid_modes or set(),
                    enrich_routes=enrich_routes,
                )
                for day in days
            ]

        working = [day.model_copy(deep=True) for day in days]
        movable_slots = [
            (day_index, item_index)
            for day_index, day in enumerate(working)
            for item_index, item in enumerate(day.items)
            if self._is_movable_activity(item)
        ]
        if len(movable_slots) >= 2:
            try:
                matrix, matrix_index = self._trip_matrix(
                    working,
                    preferred_modes=preferred_modes or set(),
                    avoid_modes=avoid_modes or set(),
                )
                working = self._improve_cross_day_assignment(
                    working,
                    movable_slots=movable_slots,
                    matrix=matrix,
                    matrix_index=matrix_index,
                )
            except Exception:
                logger.warning(
                    "Trip-level route optimization failed; keeping day allocation.",
                    exc_info=True,
                )

        return [
            self._optimize_plan_day(
                day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes or set(),
                avoid_modes=avoid_modes or set(),
                enrich_routes=enrich_routes,
            )
            for day in working
        ]

    def _optimize_plan_day(
        self,
        day: PlanDay,
        *,
        trip_start_date: str | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
        enrich_routes: bool,
    ) -> PlanDay:
        strict_source_order = any(
            item.source_order is not None or item.source_day is not None
            for item in day.items
        )
        if enrich_routes:
            items, legs = self.optimize(
                day.items,
                preserve_order=strict_source_order,
                day=day.day,
                trip_start_date=trip_start_date,
                preferred_modes=preferred_modes,
                avoid_modes=avoid_modes,
            )
        else:
            movable_positions = [
                index
                for index, item in enumerate(day.items)
                if self._is_movable_activity(item)
            ]
            items = (
                self._optimize_activity_assignments(
                    day.items,
                    movable_positions=movable_positions,
                    start=None,
                    departure_time=None,
                    preferred_modes=preferred_modes,
                    avoid_modes=avoid_modes,
                )
                if len(movable_positions) >= 2 and not strict_source_order
                else list(day.items)
            )
            legs = []
        return day.model_copy(update={"items": items, "transport_legs": legs})

    def _trip_matrix(
        self,
        days: list[PlanDay],
        *,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> tuple[list[list[float]], dict[str, int]]:
        located: list[PlanItem] = []
        seen: set[str] = set()
        for day in days:
            for item in day.items:
                identity = self._item_identity(item)
                if item.latitude is None or item.longitude is None or identity in seen:
                    continue
                seen.add(identity)
                located.append(item)
        coordinates = [(item.latitude, item.longitude) for item in located]
        mode = self._matrix_transport_mode(preferred_modes, avoid_modes)
        matrix: list[list[float]] | None = None
        if self.matrix_provider is not None and coordinates:
            result = self.matrix_provider.calculate(
                coordinates,
                transport_mode=mode,
                departure_time=None,
            )
            if result is not None and self._valid_matrix(
                result.travel_times_seconds,
                len(coordinates),
            ):
                matrix = [
                    [
                        float(value) if value is not None else float("inf")
                        for value in row
                    ]
                    for row in result.travel_times_seconds
                ]
        if matrix is None:
            matrix = self._geodesic_matrix(coordinates)
        return matrix, {
            self._item_identity(item): index for index, item in enumerate(located)
        }

    def _improve_cross_day_assignment(
        self,
        days: list[PlanDay],
        *,
        movable_slots: list[tuple[int, int]],
        matrix: list[list[float]],
        matrix_index: dict[str, int],
    ) -> list[PlanDay]:
        working = [day.model_copy(deep=True) for day in days]
        day_costs = self._day_costs(working, matrix, matrix_index)
        best_cost = sum(day_costs)
        improved = True
        while improved:
            improved = False
            for left_index, left_slot in enumerate(movable_slots[:-1]):
                for right_slot in movable_slots[left_index + 1 :]:
                    if left_slot[0] == right_slot[0]:
                        continue
                    candidate = [day.model_copy(deep=True) for day in working]
                    left_item = working[left_slot[0]].items[left_slot[1]]
                    right_item = working[right_slot[0]].items[right_slot[1]]
                    left_window = right_item.time_window
                    right_window = left_item.time_window
                    if not self._item_fits_window(left_item, left_window):
                        continue
                    if not self._item_fits_window(right_item, right_window):
                        continue
                    self._swap_slot_items(candidate, left_slot, right_slot)
                    candidate_day_costs = self._day_costs(
                        candidate,
                        matrix,
                        matrix_index,
                    )
                    cost = sum(candidate_day_costs)
                    affected_days = {left_slot[0], right_slot[0]}
                    does_not_worsen_a_day = all(
                        candidate_day_costs[index] <= day_costs[index] + 1.0
                        for index in affected_days
                    )
                    if cost + 1.0 < best_cost and does_not_worsen_a_day:
                        working = candidate
                        best_cost = cost
                        day_costs = candidate_day_costs
                        improved = True
            # Continue until a complete pair-swap pass cannot improve the trip.
        return working

    def _day_costs(
        self,
        days: list[PlanDay],
        matrix: list[list[float]],
        matrix_index: dict[str, int],
    ) -> list[float]:
        activity_minutes = [
            sum(
                item.duration_minutes or 0
                for item in day.items
                if item.timeline_category == "activity"
            )
            for day in days
        ]
        target_minutes = sum(activity_minutes) / len(days) if days else 0
        costs: list[float] = []
        for day in days:
            path = [
                matrix_index[self._item_identity(item)]
                for item in day.items
                if self._item_identity(item) in matrix_index
            ]
            travel_cost = sum(
                matrix[origin][destination]
                for origin, destination in zip(path, path[1:])
            )
            day_minutes = sum(
                item.duration_minutes or 0
                for item in day.items
                if item.timeline_category == "activity"
            )
            overflow_penalty = (
                max(
                    0,
                    day_minutes - DAILY_ACTIVITY_MINUTES,
                )
                * 60
                * 10
            )
            balance_penalty = abs(day_minutes - target_minutes) * 60
            timing_penalty = sum(
                PREFERRED_TIME_WINDOW_MISS_PENALTY_SECONDS
                for item in day.items
                if item.preferred_time_windows
                and not time_window_matches_preference(
                    item.time_window,
                    item.duration_minutes or 0,
                    item.preferred_time_windows,
                )
            )
            costs.append(
                travel_cost
                + overflow_penalty
                + balance_penalty
                + timing_penalty
            )
        return costs

    @staticmethod
    def _swap_slot_items(
        days: list[PlanDay],
        left_slot: tuple[int, int],
        right_slot: tuple[int, int],
    ) -> None:
        left_day, left_index = left_slot
        right_day, right_index = right_slot
        left_item = days[left_day].items[left_index]
        right_item = days[right_day].items[right_index]
        days[left_day].items[left_index] = right_item.model_copy(
            update={
                "time_window": left_item.time_window,
                "role": left_item.role,
            }
        )
        days[right_day].items[right_index] = left_item.model_copy(
            update={
                "time_window": right_item.time_window,
                "role": right_item.role,
            }
        )

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
        common = {
            "start": start,
            "day": day,
            "trip_start_date": trip_start_date,
            "preferred_modes": preferred_modes or set(),
            "avoid_modes": avoid_modes or set(),
        }
        if preserve_order:
            return self.legacy_optimizer.optimize(
                items,
                preserve_order=True,
                **common,
            )

        movable_positions = [
            index for index, item in enumerate(items) if self._is_movable_activity(item)
        ]
        if len(movable_positions) < 2:
            return self.legacy_optimizer.optimize(
                items,
                preserve_order=True,
                **common,
            )

        try:
            optimized = self._optimize_activity_assignments(
                items,
                movable_positions=movable_positions,
                start=start,
                departure_time=self._departure_time(
                    day=day,
                    trip_start_date=trip_start_date,
                ),
                preferred_modes=preferred_modes or set(),
                avoid_modes=avoid_modes or set(),
            )
        except Exception:
            logger.warning(
                "Route-first itinerary optimization failed; preserving PlaceSelector order.",
                exc_info=True,
            )
            optimized = list(items)

        # The legacy component remains the single route-enrichment boundary.
        # Passing preserve_order=True prevents it from undoing this assignment.
        return self.legacy_optimizer.optimize(
            optimized,
            preserve_order=True,
            **common,
        )

    def _optimize_activity_assignments(
        self,
        items: list[PlanItem],
        *,
        movable_positions: list[int],
        start: tuple[float, float] | None,
        departure_time: datetime | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> list[PlanItem]:
        located_positions = [
            index
            for index, item in enumerate(items)
            if item.latitude is not None and item.longitude is not None
        ]
        matrix, offset = self._cost_matrix(
            items,
            located_positions=located_positions,
            start=start,
            departure_time=departure_time,
            preferred_modes=preferred_modes,
            avoid_modes=avoid_modes,
        )
        matrix_index = {
            item_position: index + offset
            for index, item_position in enumerate(located_positions)
        }
        movable_items = [items[index] for index in movable_positions]
        candidate_orders = self._candidate_orders(movable_items)
        best_order = min(
            candidate_orders,
            key=lambda order: self._assignment_cost(
                items,
                movable_positions=movable_positions,
                ordered_items=order,
                matrix=matrix,
                matrix_index=matrix_index,
                start_matrix_index=0 if start is not None else None,
            ),
        )

        optimized = list(items)
        for position, selected in zip(movable_positions, best_order):
            slot = items[position]
            optimized[position] = selected.model_copy(
                update={
                    "time_window": slot.time_window,
                    "role": slot.role,
                }
            )
        return optimized

    def _cost_matrix(
        self,
        items: list[PlanItem],
        *,
        located_positions: list[int],
        start: tuple[float, float] | None,
        departure_time: datetime | None,
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> tuple[list[list[float]], int]:
        coordinates = [
            *([start] if start is not None else []),
            *[
                (items[index].latitude, items[index].longitude)
                for index in located_positions
            ],
        ]
        transport_mode = self._matrix_transport_mode(
            preferred_modes,
            avoid_modes,
        )
        if self.matrix_provider is not None:
            result = self.matrix_provider.calculate(
                coordinates,
                transport_mode=transport_mode,
                departure_time=departure_time,
            )
            if result is not None and self._valid_matrix(
                result.travel_times_seconds,
                len(coordinates),
            ):
                return [
                    [
                        float(value) if value is not None else float("inf")
                        for value in row
                    ]
                    for row in result.travel_times_seconds
                ], (1 if start is not None else 0)

        return self._geodesic_matrix(coordinates), (1 if start is not None else 0)

    @staticmethod
    def _matrix_transport_mode(
        preferred_modes: set[str],
        avoid_modes: set[str],
    ) -> str:
        normalized_preferred = {value.casefold() for value in preferred_modes}
        normalized_avoid = {value.casefold() for value in avoid_modes}
        return (
            "pedestrian"
            if "walk" in normalized_preferred
            and not normalized_preferred.intersection(
                {"car", "private_car", "ride_hailing", "taxi"}
            )
            and "walk" not in normalized_avoid
            else "car"
        )

    def _assignment_cost(
        self,
        items: list[PlanItem],
        *,
        movable_positions: list[int],
        ordered_items: tuple[PlanItem, ...],
        matrix: list[list[float]],
        matrix_index: dict[int, int],
        start_matrix_index: int | None,
    ) -> float:
        original_position_by_identity = {
            id(item): position for position, item in enumerate(items)
        }
        assigned = dict(zip(movable_positions, ordered_items))
        path: list[int] = []
        timing_penalty = 0
        if start_matrix_index is not None:
            path.append(start_matrix_index)
        for position, item in enumerate(items):
            selected = assigned.get(position, item)
            if selected.preferred_time_windows and not time_window_matches_preference(
                item.time_window,
                selected.duration_minutes or 0,
                selected.preferred_time_windows,
            ):
                timing_penalty += PREFERRED_TIME_WINDOW_MISS_PENALTY_SECONDS
            source_position = original_position_by_identity[id(selected)]
            matrix_position = matrix_index.get(source_position)
            if matrix_position is not None:
                path.append(matrix_position)
        return timing_penalty + sum(
            matrix[origin][destination] for origin, destination in zip(path, path[1:])
        )

    def _candidate_orders(
        self,
        items: list[PlanItem],
    ) -> list[tuple[PlanItem, ...]]:
        if len(items) <= self.max_exact_activities:
            return list(permutations(items))
        # PlaceSelector currently creates at most five suggested activities per day.
        # This deterministic fallback keeps the boundary safe if that grows.
        return [tuple(items)]

    @staticmethod
    def _is_movable_activity(item: PlanItem) -> bool:
        return (
            item.timeline_category == "activity"
            and item.latitude is not None
            and item.longitude is not None
            and item.source_order is None
            and item.source_day is None
            and not item.locked
        )

    @staticmethod
    def _item_fits_window(item: PlanItem, time_window: str) -> bool:
        if not item.opening_hours:
            return True
        if is_24_hours(item.opening_hours):
            return True
        start = parse_clock_minutes(time_window)
        if start is None:
            return True
        duration = item.duration_minutes or 0
        end = start + duration
        return any(
            opened <= start and end <= closed
            for opened, closed in extract_time_intervals(item.opening_hours)
        )

    @staticmethod
    def _item_identity(item: PlanItem) -> str:
        return item.item_id or item.place_id or f"name:{item.name.casefold()}"

    @staticmethod
    def _valid_matrix(matrix: list[list[int | None]], size: int) -> bool:
        return len(matrix) == size and all(len(row) == size for row in matrix)

    @staticmethod
    def _geodesic_matrix(
        coordinates: list[tuple[float, float]],
    ) -> list[list[float]]:
        return [
            [_haversine_meters(origin, destination) for destination in coordinates]
            for origin in coordinates
        ]

    @staticmethod
    def _departure_time(
        *,
        day: int,
        trip_start_date: str | None,
    ) -> datetime | None:
        if trip_start_date is None:
            return None
        try:
            return datetime.fromisoformat(trip_start_date).replace(hour=8) + timedelta(
                days=day - 1
            )
        except ValueError:
            return None


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
