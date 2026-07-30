from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.modules.plans.routing.provider import (
    RouteCalculation,
    RouteTransportMode,
)


class HereRouteProvider:
    provider_name = "here_routing_v8"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 0.2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = max(min_interval_seconds, 0.0)
        self._request_lock = threading.Lock()
        self._last_request_at = 0.0
        self._cache: dict[
            tuple[tuple[float, float], tuple[float, float], str],
            RouteCalculation | None,
        ] = {}

    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        transport_mode: RouteTransportMode,
    ) -> RouteCalculation | None:
        cache_key = (origin, destination, transport_mode)
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            payload = self._request_json(
                params={
                    "origin": _format_coordinate(origin),
                    "destination": _format_coordinate(destination),
                    "transportMode": transport_mode,
                    "routingMode": "fast",
                    "return": "polyline,summary",
                    # The plan currently has no travel date. Avoid applying
                    # today's traffic to a future itinerary.
                    "departureTime": "any",
                    "apiKey": self.api_key,
                }
            )
            result = _parse_route(payload, provider=self.provider_name)
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            result = None
        self._cache[cache_key] = result
        return result

    def _request_json(self, *, params: dict[str, str]) -> Any:
        with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait_for = self.min_interval_seconds - elapsed
            if wait_for > 0:
                time.sleep(wait_for)
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.get(f"{self.base_url}/v8/routes", params=params)
            self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.json()


def _parse_route(payload: Any, *, provider: str) -> RouteCalculation:
    if not isinstance(payload, dict):
        raise ValueError("HERE route response must be an object.")
    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        raise ValueError("HERE route response contains no routes.")
    first_route = routes[0] if isinstance(routes[0], dict) else {}
    sections = first_route.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("HERE route response contains no sections.")

    distance_meters = 0
    duration_seconds = 0
    geometry: list[tuple[float, float]] = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("HERE route section must be an object.")
        summary = section.get("summary")
        if not isinstance(summary, dict):
            raise ValueError("HERE route section is missing summary.")
        distance_meters += _non_negative_int(summary.get("length"))
        duration_seconds += _non_negative_int(summary.get("duration"))
        encoded_polyline = section.get("polyline")
        if not isinstance(encoded_polyline, str) or not encoded_polyline:
            raise ValueError("HERE route section is missing polyline.")
        section_geometry = decode_flexible_polyline(encoded_polyline)
        if geometry and section_geometry and geometry[-1] == section_geometry[0]:
            section_geometry = section_geometry[1:]
        geometry.extend(section_geometry)

    if len(geometry) < 2:
        raise ValueError("HERE route geometry must contain at least two points.")
    return RouteCalculation(
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
        geometry_coordinates=geometry,
        provider=provider,
        fetched_at=datetime.now(timezone.utc),
    )


def decode_flexible_polyline(value: str) -> list[tuple[float, float]]:
    """Decode the 2D geometry returned by HERE Routing API v8."""
    values = iter(_decode_unsigned_values(value))
    try:
        version = next(values)
        header = next(values)
    except StopIteration as exc:
        raise ValueError("Invalid flexible polyline header.") from exc
    if version != 1:
        raise ValueError("Unsupported flexible polyline version.")

    precision = header & 15
    third_dimension = (header >> 4) & 7
    factor = 10**precision
    third_factor = 10 ** ((header >> 7) & 15)
    latitude = 0
    longitude = 0
    third_value = 0
    coordinates: list[tuple[float, float]] = []
    while True:
        try:
            latitude += _to_signed(next(values))
            longitude += _to_signed(next(values))
            if third_dimension:
                third_value += _to_signed(next(values))
                _ = third_value / third_factor
        except StopIteration:
            break
        coordinates.append((latitude / factor, longitude / factor))
    return coordinates


def _decode_unsigned_values(value: str) -> list[int]:
    alphabet = (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )
    decoding = {character: index for index, character in enumerate(alphabet)}
    result: list[int] = []
    current = 0
    shift = 0
    for character in value:
        if character not in decoding:
            raise ValueError("Invalid flexible polyline character.")
        chunk = decoding[character]
        current |= (chunk & 0x1F) << shift
        if chunk & 0x20:
            shift += 5
            continue
        result.append(current)
        current = 0
        shift = 0
    if shift:
        raise ValueError("Invalid flexible polyline encoding.")
    return result


def _to_signed(value: int) -> int:
    return ~(value >> 1) if value & 1 else value >> 1


def _format_coordinate(coordinate: tuple[float, float]) -> str:
    return f"{coordinate[0]:.7f},{coordinate[1]:.7f}"


def _non_negative_int(value: Any) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError("HERE route summary values cannot be negative.")
    return parsed
