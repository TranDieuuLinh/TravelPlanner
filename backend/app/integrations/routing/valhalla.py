from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.routing.polyline import decode_polyline
from app.modules.plans.routing.provider import (
    RouteCalculation,
    RouteTransportMode,
)


class ValhallaRouteProvider:
    provider_name = "valhalla_routing"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = max(min_interval_seconds, 0.0)
        self._request_lock = threading.Lock()
        self._last_request_at = 0.0
        self._cache: dict[
            tuple[tuple[float, float], tuple[float, float], str, str],
            RouteCalculation | None,
        ] = {}

    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        transport_mode: RouteTransportMode,
        departure_time: datetime | None = None,
    ) -> RouteCalculation | None:
        routes = self.calculate_many(
            [origin, destination],
            transport_mode=transport_mode,
            departure_time=departure_time,
        )
        return routes[0] if routes else None

    def calculate_many(
        self,
        coordinates: list[tuple[float, float]],
        *,
        transport_mode: RouteTransportMode,
        departure_time: datetime | None = None,
    ) -> list[RouteCalculation] | None:
        """Calculate every adjacent leg of one ordered path with one request."""
        if len(coordinates) < 2:
            return []
        departure_value = (
            departure_time.strftime("%Y-%m-%dT%H:%M")
            if departure_time is not None
            else ""
        )
        cache_keys = [
            (
                origin,
                destination,
                transport_mode,
                departure_value,
            )
            for origin, destination in zip(coordinates, coordinates[1:])
        ]
        if all(cache_key in self._cache for cache_key in cache_keys):
            cached = [self._cache[cache_key] for cache_key in cache_keys]
            return (
                [route for route in cached if route is not None]
                if all(route is not None for route in cached)
                else None
            )

        body: dict[str, Any] = {
            "locations": [_location(coordinate) for coordinate in coordinates],
            "costing": _costing(transport_mode),
            "units": "kilometers",
            "language": "vi-VN",
        }
        if departure_time is not None:
            body["date_time"] = {
                "type": 1,
                "value": departure_value,
            }
        try:
            payload = self._request_json("/route", body=body)
            routes = _parse_route_legs(
                payload,
                provider=self.provider_name,
                expected_leg_count=len(coordinates) - 1,
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            routes = None
        if routes is None:
            for cache_key in cache_keys:
                self._cache[cache_key] = None
            return None
        for cache_key, route in zip(cache_keys, routes):
            self._cache[cache_key] = route
        return routes

    def _request_json(self, path: str, *, body: dict[str, Any]) -> Any:
        with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait_for = self.min_interval_seconds - elapsed
            if wait_for > 0:
                time.sleep(wait_for)
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.base_url}{path}", json=body)
            self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.json()


def _parse_route(payload: Any, *, provider: str) -> RouteCalculation:
    return _parse_route_legs(
        payload,
        provider=provider,
        expected_leg_count=1,
    )[0]


def _parse_route_legs(
    payload: Any,
    *,
    provider: str,
    expected_leg_count: int,
) -> list[RouteCalculation]:
    if not isinstance(payload, dict):
        raise ValueError("Valhalla route response must be an object.")
    trip = payload.get("trip")
    if not isinstance(trip, dict):
        raise ValueError("Valhalla route response is missing trip.")
    summary = trip.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Valhalla route response is missing summary.")
    legs = trip.get("legs")
    if not isinstance(legs, list) or len(legs) != expected_leg_count or not legs:
        raise ValueError("Valhalla route response contains no legs.")
    fetched_at = datetime.now(timezone.utc)
    routes: list[RouteCalculation] = []
    for leg_index, leg in enumerate(legs):
        if not isinstance(leg, dict):
            raise ValueError("Valhalla route leg must be an object.")
        shape = leg.get("shape")
        if not isinstance(shape, str) or not shape:
            raise ValueError("Valhalla route leg is missing shape.")
        geometry = decode_polyline(shape, precision=6)
        if len(geometry) < 2:
            raise ValueError("Valhalla route geometry must contain two points.")
        leg_summary = leg.get("summary")
        if not isinstance(leg_summary, dict):
            if expected_leg_count != 1 or leg_index != 0:
                raise ValueError("Valhalla route leg is missing summary.")
            leg_summary = summary
        routes.append(
            RouteCalculation(
                distance_meters=round(
                    _non_negative_float(leg_summary.get("length")) * 1000
                ),
                duration_seconds=round(_non_negative_float(leg_summary.get("time"))),
                geometry_coordinates=geometry,
                provider=provider,
                fetched_at=fetched_at,
            )
        )
    return routes


def _location(coordinate: tuple[float, float]) -> dict[str, float]:
    return {"lat": coordinate[0], "lon": coordinate[1]}


def _costing(transport_mode: RouteTransportMode) -> str:
    return "pedestrian" if transport_mode == "pedestrian" else "auto"


def _non_negative_float(value: Any) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError("Valhalla route summary cannot be negative.")
    return parsed
