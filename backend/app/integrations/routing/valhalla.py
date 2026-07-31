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
        departure_value = (
            departure_time.strftime("%Y-%m-%dT%H:%M")
            if departure_time is not None
            else ""
        )
        cache_key = (
            origin,
            destination,
            transport_mode,
            departure_value,
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        body: dict[str, Any] = {
            "locations": [
                _location(origin),
                _location(destination),
            ],
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
            result = _parse_route(payload, provider=self.provider_name)
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            result = None
        self._cache[cache_key] = result
        return result

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
    if not isinstance(payload, dict):
        raise ValueError("Valhalla route response must be an object.")
    trip = payload.get("trip")
    if not isinstance(trip, dict):
        raise ValueError("Valhalla route response is missing trip.")
    summary = trip.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Valhalla route response is missing summary.")
    legs = trip.get("legs")
    if not isinstance(legs, list) or not legs:
        raise ValueError("Valhalla route response contains no legs.")

    geometry: list[tuple[float, float]] = []
    for leg in legs:
        if not isinstance(leg, dict):
            raise ValueError("Valhalla route leg must be an object.")
        shape = leg.get("shape")
        if not isinstance(shape, str) or not shape:
            raise ValueError("Valhalla route leg is missing shape.")
        leg_geometry = decode_polyline(shape, precision=6)
        if geometry and leg_geometry and geometry[-1] == leg_geometry[0]:
            leg_geometry = leg_geometry[1:]
        geometry.extend(leg_geometry)
    if len(geometry) < 2:
        raise ValueError("Valhalla route geometry must contain two points.")

    return RouteCalculation(
        distance_meters=round(_non_negative_float(summary.get("length")) * 1000),
        duration_seconds=round(_non_negative_float(summary.get("time"))),
        geometry_coordinates=geometry,
        provider=provider,
        fetched_at=datetime.now(timezone.utc),
    )


def _location(coordinate: tuple[float, float]) -> dict[str, float]:
    return {"lat": coordinate[0], "lon": coordinate[1]}


def _costing(transport_mode: RouteTransportMode) -> str:
    return "pedestrian" if transport_mode == "pedestrian" else "auto"


def _non_negative_float(value: Any) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError("Valhalla route summary cannot be negative.")
    return parsed
