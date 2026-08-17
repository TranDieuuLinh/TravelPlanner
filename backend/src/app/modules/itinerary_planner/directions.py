from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, Request

from app.modules.itinerary_planner.directions_contract import (
    CurrentLocationRouteRequest,
    DayDirectionsRequest,
    DirectionsDestination,
    DirectionsOrigin,
    DirectionsResponseLeg,
)
from app.modules.itinerary_planner.ports import RouteDetailProvider
from app.modules.itinerary_planner.routing_models import (
    MatrixLocation,
    RouteLegRequest,
)


def _profile(requested_mode: str | None) -> str:
    return {
        "walk": "pedestrian",
        "car": "auto",
        "bus": "auto",
    }.get(requested_mode or "car", "auto")


def _mode(requested_mode: str | None) -> str:
    if requested_mode in {"walk", "pedestrian"}:
        return "walk"
    if requested_mode == "bus":
        return "bus"
    return "car"


def _decode_polyline6(encoded: str) -> list[tuple[float, float]]:
    coordinates: list[tuple[float, float]] = []
    index = latitude = longitude = 0
    while index < len(encoded):
        latitude, index = _decode_component(encoded, index, latitude)
        longitude, index = _decode_component(encoded, index, longitude)
        coordinates.append((latitude / 1_000_000, longitude / 1_000_000))
    return coordinates


def _decode_component(encoded: str, index: int, previous: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if index >= len(encoded):
            raise ValueError("truncated Valhalla polyline")
        value = ord(encoded[index]) - 63
        index += 1
        result |= (value & 0x1F) << shift
        shift += 5
        if value < 0x20:
            break
    delta = ~(result >> 1) if result & 1 else result >> 1
    return previous + delta, index


def _location(node_id: str, point: DirectionsOrigin) -> MatrixLocation:
    return MatrixLocation(
        node_id=node_id,
        latitude=point.latitude,
        longitude=point.longitude,
        canonical_key=f"{point.latitude:.6f},{point.longitude:.6f}",
    )


class DirectionsService:
    def __init__(self, provider: RouteDetailProvider) -> None:
        self.provider = provider

    async def current_location_route(
        self, request: CurrentLocationRouteRequest
    ) -> DirectionsResponseLeg:
        details = await self._route(
            request.origin,
            (request.destination,),
            _profile(request.preferred_modes[0] if request.preferred_modes else None),
        )
        return self._response_leg(
            details[0],
            request.origin,
            request.destination,
            _mode(request.preferred_modes[0] if request.preferred_modes else None),
        )

    async def day_directions(
        self, request: DayDirectionsRequest
    ) -> list[DirectionsResponseLeg]:
        details = await self._route(
            request.origin, tuple(request.destinations), _profile(request.requested_mode)
        )
        mode = _mode(request.requested_mode)
        origin = request.origin
        result: list[DirectionsResponseLeg] = []
        for detail, destination in zip(details, request.destinations, strict=True):
            result.append(self._response_leg(detail, origin, destination, mode))
            origin = destination
        return result

    async def _route(
        self,
        origin: DirectionsOrigin,
        destinations: tuple[DirectionsDestination, ...],
        profile: str,
    ):
        points = (origin, *destinations)
        locations = tuple(_location(f"directions-{index}", point) for index, point in enumerate(points))
        legs = tuple(
            RouteLegRequest(locations[index], locations[index + 1])
            for index in range(len(locations) - 1)
        )
        return await self.provider.route(legs, profile)

    @staticmethod
    def _response_leg(detail, origin: DirectionsOrigin, destination: DirectionsDestination, mode: str):
        try:
            coordinates = _decode_polyline6(detail.encoded_polyline) if detail.encoded_polyline else []
        except ValueError:
            coordinates = []
        if len(coordinates) < 2:
            coordinates = [
                (origin.latitude, origin.longitude),
                (destination.latitude, destination.longitude),
            ]
        provider = detail.provider
        return DirectionsResponseLeg(
            mode=mode,
            distance_meters=ceil(detail.distance_meters),
            estimated_duration_minutes=ceil(detail.duration_seconds / 60),
            geometry_coordinates=coordinates,
            source="valhalla_routing" if provider == "valhalla" else provider,
            verified=provider == "valhalla",
            from_item_id=None,
            to_item_id=destination.item_id,
            from_place=origin.name or "Vị trí hiện tại",
            to_place=destination.name or "Điểm đến",
        )


def get_directions_service(request: Request) -> DirectionsService:
    return request.app.state.directions_service


router = APIRouter(prefix="/v1/plans", tags=["directions"])


@router.post("/current-location-route", response_model=DirectionsResponseLeg)
async def current_location_route(
    payload: CurrentLocationRouteRequest,
    service: DirectionsService = Depends(get_directions_service),
) -> DirectionsResponseLeg:
    return await service.current_location_route(payload)


@router.post("/day-directions", response_model=list[DirectionsResponseLeg])
async def day_directions(
    payload: DayDirectionsRequest,
    service: DirectionsService = Depends(get_directions_service),
) -> list[DirectionsResponseLeg]:
    return await service.day_directions(payload)
