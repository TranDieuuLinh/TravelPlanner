from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.modules.itinerary_planner.routing_models import (
    MatrixCell,
    MatrixLocation,
    RouteDetail,
    RouteLegRequest,
    STRAIGHT_LINE_PROVIDER,
    TravelMatrix,
)


EARTH_RADIUS_METERS = 6_371_000
STRAIGHT_LINE_VERSION = "v1"
POLYLINE_SCALE = 1_000_000
PROFILE_SPEED_KMH = {
    "auto": 30.0,
    "bicycle": 15.0,
    "pedestrian": 5.0,
}


class StraightLineRoutingAdapter:
    """Approximate routing using great-circle distance and a direct polyline."""

    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        speed_mps = _speed_mps(profile)
        rows = []
        for origin in locations:
            row = []
            for destination in locations:
                distance = great_circle_distance(origin, destination)
                row.append(
                    MatrixCell(
                        duration_seconds=distance / speed_mps,
                        distance_meters=distance,
                        reachable=True,
                    )
                )
            rows.append(tuple(row))
        return TravelMatrix(
            node_ids=tuple(location.node_id for location in locations),
            cells=tuple(rows),
            profile=profile,
            provider=STRAIGHT_LINE_PROVIDER,
            provider_version=STRAIGHT_LINE_VERSION,
        )

    async def route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]:
        speed_mps = _speed_mps(profile)
        return tuple(
            _route_detail(leg, speed_mps)
            for leg in legs
        )


def great_circle_distance(
    origin: MatrixLocation,
    destination: MatrixLocation,
) -> float:
    latitude_delta = radians(destination.latitude - origin.latitude)
    longitude_delta = radians(destination.longitude - origin.longitude)
    origin_latitude = radians(origin.latitude)
    destination_latitude = radians(destination.latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(origin_latitude)
        * cos(destination_latitude)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(min(1.0, haversine)))


def _route_detail(leg: RouteLegRequest, speed_mps: float) -> RouteDetail:
    distance = great_circle_distance(leg.origin, leg.destination)
    return RouteDetail(
        origin_node_id=leg.origin.node_id,
        destination_node_id=leg.destination.node_id,
        duration_seconds=distance / speed_mps,
        distance_meters=distance,
        encoded_polyline=_encode_polyline(
            (
                (leg.origin.latitude, leg.origin.longitude),
                (leg.destination.latitude, leg.destination.longitude),
            )
        ),
        provider=STRAIGHT_LINE_PROVIDER,
    )


def _speed_mps(profile: str) -> float:
    try:
        return PROFILE_SPEED_KMH[profile] / 3.6
    except KeyError as exc:
        raise ValueError(f"Unsupported straight-line profile: {profile}") from exc


def _encode_polyline(points: tuple[tuple[float, float], ...]) -> str:
    encoded: list[str] = []
    previous_latitude = 0
    previous_longitude = 0
    for latitude, longitude in points:
        for value, previous in (
            (latitude, previous_latitude),
            (longitude, previous_longitude),
        ):
            scaled = int(round(value * POLYLINE_SCALE))
            delta = scaled - previous
            shifted = ~(delta << 1) if delta < 0 else delta << 1
            while shifted >= 0x20:
                encoded.append(chr((0x20 | (shifted & 0x1F)) + 63))
                shifted >>= 5
            encoded.append(chr(shifted + 63))
        previous_latitude = int(round(latitude * POLYLINE_SCALE))
        previous_longitude = int(round(longitude * POLYLINE_SCALE))
    return "".join(encoded)
