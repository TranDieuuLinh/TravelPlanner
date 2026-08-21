from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from math import ceil
from time import monotonic
from typing import Any

from app.modules.itinerary_planner.day_repair.models import (
    DayScheduleRepair,
    RepairAnchors,
    RepairStop,
)
from app.modules.itinerary_planner.day_repair.costs import update_day_costs
from app.modules.itinerary_planner.day_repair.scheduler import (
    repair_fixed_order,
    repair_with_cp_sat,
)
from app.modules.itinerary_planner.day_repair.windows import (
    intersect_ranges,
    parse_opening_hours,
    start_ranges,
)
from app.modules.itinerary_planner.policies import (
    ITINERARY_START_MINUTE,
    MEAL_POLICIES,
)
from app.modules.itinerary_planner.ports import (
    RouteDetailProvider,
    RoutingMatrixProvider,
)
from app.modules.itinerary_planner.routing import ROUTING_PROFILE, safe_travel
from app.modules.itinerary_planner.routing_models import (
    MatrixLocation,
    RouteLegRequest,
    RoutingPhaseError,
)
from app.shared.tools.transport_cost import TransportCostEstimator


class DayRepairError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _RepairContext:
    output: dict[str, Any]
    raw_day: dict[str, Any]
    stop_by_internal_id: dict[str, dict[str, Any]]
    locations: dict[str, MatrixLocation]
    repair_stops: tuple[RepairStop, ...]
    anchors: RepairAnchors
    people: int


class DayRepairService:
    def __init__(
        self,
        matrix_provider: RoutingMatrixProvider,
        route_provider: RouteDetailProvider,
        estimator: TransportCostEstimator,
    ) -> None:
        self.matrix_provider = matrix_provider
        self.route_provider = route_provider
        self.estimator = estimator

    async def repair(
        self,
        output: dict[str, Any] | None,
        *,
        day: int,
        item_id: str,
        replacement: dict[str, Any],
    ) -> dict[str, Any]:
        started = monotonic()
        has_opening_hours = parse_opening_hours(
            replacement.get("openingHours")
        ) is not None
        context = self._prepare_context(output, day, item_id, replacement)
        travel = await self._travel_minutes(context)
        schedule = repair_fixed_order(
            context.repair_stops, travel, context.anchors
        )
        if schedule is None:
            schedule = await asyncio.to_thread(
                repair_with_cp_sat,
                context.repair_stops,
                travel,
                context.anchors,
            )
        if schedule is None:
            raise DayRepairError(
                "DAY_REPAIR_INFEASIBLE",
                "Địa điểm mới không thể xếp cùng các điểm hiện tại theo giờ mở cửa và thời gian di chuyển.",
            )
        await self._apply_schedule(context, schedule, travel)
        elapsed_ms = round((monotonic() - started) * 1000)
        timings = context.output.setdefault("phaseTimingsMs", {})
        if isinstance(timings, dict):
            timings["manualDayRepair"] = elapsed_ms
        warnings = context.output.setdefault("warnings", [])
        if isinstance(warnings, list):
            message = (
                f"Ngày {day} được tính lại sau khi thay địa điểm; "
                + (
                    "giữ nguyên thứ tự các điểm."
                    if schedule.strategy == "fixed_order_reflow"
                    else "thứ tự được điều chỉnh để giữ lịch khả thi."
                )
            )
            warnings[:] = [item for item in warnings if not str(item).startswith(f"Ngày {day} được tính lại")]
            warnings.append(message)
            if not has_opening_hours:
                warnings.append(
                    f"Chưa có giờ mở cửa đã xác minh cho {replacement.get('name', 'địa điểm mới')}; "
                    "repair tạm dùng khung giờ mặc định."
                )
        return context.output

    def _prepare_context(
        self,
        output: dict[str, Any] | None,
        day: int,
        item_id: str,
        replacement: dict[str, Any],
    ) -> _RepairContext:
        if not isinstance(output, dict):
            raise DayRepairError("PLAN_NOT_FOUND", "Chưa có lịch trình để sửa.")
        copied = deepcopy(output)
        raw_days = copied.get("days")
        if not isinstance(raw_days, list):
            raise DayRepairError("DAY_NOT_FOUND", "Không tìm thấy ngày trong lịch trình.")
        raw_day = next(
            (item for item in raw_days if isinstance(item, dict) and item.get("day") == day),
            None,
        )
        if raw_day is None or not isinstance(raw_day.get("stops"), list):
            raise DayRepairError("DAY_NOT_FOUND", "Không tìm thấy ngày trong lịch trình.")
        stops = tuple(item for item in raw_day["stops"] if isinstance(item, dict))
        target = self._find_stop(stops, day, item_id)
        self._replace_stop(target, replacement, day)
        stop_by_id: dict[str, dict[str, Any]] = {}
        locations: dict[str, MatrixLocation] = {}
        repair_stops: list[RepairStop] = []
        for index, stop in enumerate(stops):
            internal_id = str(stop.get("itemId") or f"legacy:{day}:{index}")
            if internal_id in stop_by_id:
                internal_id = f"{internal_id}:{index}"
            coordinates = stop.get("coordinates")
            if not isinstance(coordinates, dict):
                raise DayRepairError("MISSING_COORDINATES", f"{stop.get('name', 'Địa điểm')} chưa có tọa độ.")
            try:
                latitude = float(coordinates["latitude"])
                longitude = float(coordinates["longitude"])
            except (KeyError, TypeError, ValueError) as exc:
                raise DayRepairError("MISSING_COORDINATES", f"{stop.get('name', 'Địa điểm')} chưa có tọa độ.") from exc
            duration = max(1, int(stop.get("durationMinutes") or 60))
            candidate_ranges = start_ranges(stop, day, duration)
            if not candidate_ranges:
                raise DayRepairError(
                    "PLACE_CLOSED",
                    f"{stop.get('name', 'Địa điểm')} không có khung giờ đủ dài trong ngày này.",
                )
            meal_type = str(stop.get("mealType")) if stop.get("mealType") else None
            if meal_type in {meal.value for meal in MEAL_POLICIES}:
                policy = next(
                    value for meal, value in MEAL_POLICIES.items() if meal.value == meal_type
                )
                candidate_ranges = intersect_ranges(
                    candidate_ranges, policy.earliest_start, policy.latest_start
                )
                if not candidate_ranges:
                    raise DayRepairError(
                        "MEAL_WINDOW_CONFLICT",
                        f"{stop.get('name', 'Địa điểm')} không mở trong khung giờ {meal_type}.",
                    )
            stop_by_id[internal_id] = stop
            locations[internal_id] = MatrixLocation(
                internal_id,
                latitude,
                longitude,
                f"geo:{latitude:.6f},{longitude:.6f}",
            )
            repair_stops.append(
                RepairStop(
                    internal_id,
                    duration,
                    int(stop.get("startMinute") or ITINERARY_START_MINUTE),
                    candidate_ranges,
                    meal_type,
                )
            )
        anchors = self._anchors(copied, day, len(raw_days), locations)
        return _RepairContext(
            copied,
            raw_day,
            stop_by_id,
            locations,
            tuple(repair_stops),
            anchors,
            max(1, int(copied.get("people") or 1)),
        )

    @staticmethod
    def _find_stop(
        stops: tuple[dict[str, Any], ...], day: int, item_id: str
    ) -> dict[str, Any]:
        for index, stop in enumerate(stops):
            legacy_id = f"planner-{day}-{index + 1}-{stop.get('placeId', '')}"
            if stop.get("itemId") == item_id or legacy_id == item_id:
                return stop
        raise DayRepairError("ITEM_NOT_FOUND", "Không tìm thấy địa điểm trong lịch trình.")

    def _replace_stop(
        self, stop: dict[str, Any], replacement: dict[str, Any], day: int
    ) -> None:
        previous_meal = stop.get("mealType")
        place_type = str(replacement.get("placeType") or "").casefold()
        kind = (
            "food"
            if place_type in {"food", "restaurant", "drink_dessert"}
            else "entertainment"
            if place_type == "entertainment"
            else "place"
        )
        if previous_meal and kind != "food":
            raise DayRepairError(
                "MEAL_REPLACEMENT_TYPE_CONFLICT",
                "Điểm ăn uống phải được thay bằng một địa điểm ăn uống khác để giữ đủ bữa.",
            )
        try:
            latitude = float(replacement["latitude"])
            longitude = float(replacement["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DayRepairError(
                "MISSING_COORDINATES", "Địa điểm mới chưa có tọa độ hợp lệ."
            ) from exc
        duration = max(1, int(replacement.get("durationMinutes") or stop.get("durationMinutes") or 60))
        intervals = parse_opening_hours(replacement.get("openingHours"))
        stop.update(
            {
                "placeId": replacement.get("placeId") or stop.get("placeId"),
                "name": str(replacement.get("name") or "").strip(),
                "address": replacement.get("address"),
                "kind": kind,
                "coordinates": {"latitude": latitude, "longitude": longitude},
                "durationMinutes": duration,
                "endMinute": int(stop.get("startMinute") or ITINERARY_START_MINUTE) + duration,
                "openingHours": ({str(day): intervals} if intervals is not None else None),
                "rating": replacement.get("rating"),
                "reviewCount": replacement.get("reviewCount"),
                "costPerPerson": max(0, int(replacement.get("costPerPerson") or 0)),
                "imageUrls": [replacement["imageUrl"]] if replacement.get("imageUrl") else [],
                "notes": None,
                "tags": [],
                "priority": "user_input",
            }
        )

    def _anchors(
        self,
        output: dict[str, Any],
        day: int,
        day_count: int,
        locations: dict[str, MatrixLocation],
    ) -> RepairAnchors:
        accommodation = output.get("accommodation")
        if not isinstance(accommodation, dict) or not isinstance(accommodation.get("coordinates"), dict):
            return RepairAnchors()
        try:
            latitude = float(accommodation["coordinates"]["latitude"])
            longitude = float(accommodation["coordinates"]["longitude"])
        except (KeyError, TypeError, ValueError):
            return RepairAnchors()
        accommodation_id = "__repair_accommodation__"
        locations[accommodation_id] = MatrixLocation(
            accommodation_id,
            latitude,
            longitude,
            f"geo:{latitude:.6f},{longitude:.6f}",
        )
        return RepairAnchors(
            accommodation_id,
            require_start=day > 1,
            require_return=day < day_count,
        )

    async def _travel_minutes(self, context: _RepairContext) -> dict[tuple[str, str], int]:
        ordered_locations = tuple(context.locations.values())
        try:
            matrix = await self.matrix_provider.matrix(ordered_locations, ROUTING_PROFILE)
        except Exception as exc:
            raise DayRepairError(
                "ROUTING_UNAVAILABLE", "Không thể lấy thời gian di chuyển để tính lại ngày."
            ) from exc
        travel: dict[tuple[str, str], int] = {}
        for origin in ordered_locations:
            for destination in ordered_locations:
                if origin.node_id == destination.node_id:
                    continue
                cell = matrix.cell(origin.node_id, destination.node_id)
                if cell.reachable:
                    travel[(origin.node_id, destination.node_id)] = safe_travel(
                        cell, self.estimator, ROUTING_PROFILE, context.people
                    ).safe_minutes
        return travel

    async def _apply_schedule(
        self,
        context: _RepairContext,
        schedule: DayScheduleRepair,
        travel: dict[tuple[str, str], int],
    ) -> None:
        del travel
        ordered_stops: list[dict[str, Any]] = []
        for position, repaired in enumerate(schedule.stops):
            stop = context.stop_by_internal_id[repaired.internal_id]
            stop["startMinute"] = repaired.start_minute
            stop["endMinute"] = repaired.end_minute
            stop["durationMinutes"] = repaired.end_minute - repaired.start_minute
            stop["position"] = position
            ordered_stops.append(stop)
        context.raw_day["stops"] = ordered_stops
        route_nodes: list[str] = [item.internal_id for item in schedule.stops]
        if context.anchors.require_start and context.anchors.accommodation_id:
            route_nodes.insert(0, context.anchors.accommodation_id)
        if context.anchors.require_return and context.anchors.accommodation_id:
            route_nodes.append(context.anchors.accommodation_id)
        requests = tuple(
            RouteLegRequest(
                context.locations[route_nodes[index]],
                context.locations[route_nodes[index + 1]],
            )
            for index in range(len(route_nodes) - 1)
        )
        try:
            details = await self.route_provider.route(requests, ROUTING_PROFILE)
        except (RoutingPhaseError, OSError, ValueError) as exc:
            raise DayRepairError(
                "ROUTING_UNAVAILABLE", "Không thể lấy tuyến đường chi tiết sau khi xếp lịch."
            ) from exc
        if len(details) != len(requests):
            raise DayRepairError("ROUTING_UNAVAILABLE", "Dữ liệu tuyến đường trả về không đầy đủ.")
        actual_place_id = {
            internal_id: str(stop.get("placeId") or internal_id)
            for internal_id, stop in context.stop_by_internal_id.items()
        }
        accommodation = context.output.get("accommodation")
        if context.anchors.accommodation_id and isinstance(accommodation, dict):
            actual_place_id[context.anchors.accommodation_id] = str(
                accommodation.get("placeId") or context.anchors.accommodation_id
            )
        legs: list[dict[str, Any]] = []
        for pair, detail in zip(zip(route_nodes, route_nodes[1:]), details, strict=True):
            origin_id, destination_id = pair
            distance = max(0, ceil(detail.distance_meters))
            duration = max(0, ceil(detail.duration_seconds / 60))
            cost, _night = self.estimator.estimate(
                distance, ROUTING_PROFILE, context.people
            )
            legs.append(
                {
                    "fromPlaceId": actual_place_id[origin_id],
                    "toPlaceId": actual_place_id[destination_id],
                    "durationMinutes": duration,
                    "distanceMeters": distance,
                    "encodedPolyline": detail.encoded_polyline,
                    "provider": detail.provider,
                    "geometryAvailable": detail.encoded_polyline is not None,
                    "costPerPerson": cost,
                }
            )
        context.raw_day["legs"] = legs
        context.raw_day["activityMinutes"] = sum(
            int(stop.get("durationMinutes") or 0) for stop in ordered_stops
        )
        context.raw_day["travelMinutes"] = sum(leg["durationMinutes"] for leg in legs)
        update_day_costs(context.output, context.raw_day, ordered_stops, legs)
