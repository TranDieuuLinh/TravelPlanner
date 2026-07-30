from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.routing.here import decode_flexible_polyline
from app.modules.plans.routing.provider import RouteCalculation


class HereTransitRouteProvider:
    provider_name = "here_transit_v8"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        min_interval_seconds: float = 0.2,
        language: str = "vi-VN",
        max_access_walk_meters: int = 1500,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = max(min_interval_seconds, 0.0)
        self.language = language
        self.max_access_walk_meters = max_access_walk_meters
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
        departure_time: datetime | None,
        modes: tuple[str, ...] = (),
    ) -> RouteCalculation | None:
        departure_value = (
            departure_time.isoformat(timespec="seconds")
            if departure_time is not None
            else f"current-{int(time.time() // 300)}"
        )
        cache_key = (
            origin,
            destination,
            "|".join((departure_value, *modes)),
        )
        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            params = {
                "origin": _format_coordinate(origin),
                "destination": _format_coordinate(destination),
                "return": "polyline,travelSummary",
                "alternatives": "0",
                "pedestrian[maxDistance]": str(
                    self.max_access_walk_meters
                ),
                "lang": self.language,
                "apiKey": self.api_key,
            }
            if departure_time is not None:
                params["departureTime"] = departure_value
            if modes:
                params["modes"] = ",".join(modes)
            payload = self._request_json(params=params)
            result = _parse_transit_route(payload, provider=self.provider_name)
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
                response = client.get(
                    f"{self.base_url}/v8/routes",
                    params=params,
                )
            self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.json()


def _parse_transit_route(payload: Any, *, provider: str) -> RouteCalculation:
    if not isinstance(payload, dict):
        raise ValueError("HERE transit response must be an object.")
    routes = payload.get("routes")
    if not isinstance(routes, list):
        raise ValueError("HERE transit response must contain routes.")
    route = next(
        (
            candidate
            for candidate in routes
            if isinstance(candidate, dict)
            and _has_transit_section(candidate)
        ),
        None,
    )
    if route is None:
        raise ValueError("HERE returned no public-transit route.")
    sections = route.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("HERE transit route contains no sections.")

    distance_meters = 0
    travel_duration_seconds = 0
    geometry: list[tuple[float, float]] = []
    transit_modes: list[str] = []
    lines: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("HERE transit section must be an object.")
        summary = section.get("travelSummary")
        if not isinstance(summary, dict):
            raise ValueError("HERE transit section is missing travelSummary.")
        distance_meters += _non_negative_int(summary.get("length"))
        travel_duration_seconds += _non_negative_int(summary.get("duration"))
        encoded_polyline = section.get("polyline")
        if not isinstance(encoded_polyline, str) or not encoded_polyline:
            raise ValueError("HERE transit section is missing polyline.")
        section_geometry = decode_flexible_polyline(encoded_polyline)
        if geometry and section_geometry and geometry[-1] == section_geometry[0]:
            section_geometry = section_geometry[1:]
        geometry.extend(section_geometry)

        transport = section.get("transport")
        if not isinstance(transport, dict):
            continue
        mode = transport.get("mode")
        if section.get("type") == "transit" and isinstance(mode, str):
            if mode not in transit_modes:
                transit_modes.append(mode)
            line = transport.get("shortName") or transport.get("name")
            if isinstance(line, str) and line and line not in lines:
                lines.append(line)

    duration_seconds = _scheduled_duration(sections) or travel_duration_seconds
    if len(geometry) < 2:
        raise ValueError("HERE transit geometry must contain at least two points.")
    return RouteCalculation(
        distance_meters=distance_meters,
        duration_seconds=duration_seconds,
        geometry_coordinates=geometry,
        provider=provider,
        fetched_at=datetime.now(timezone.utc),
        details={
            "transitModes": transit_modes,
            "lines": lines,
        },
    )


def _has_transit_section(route: dict[str, Any]) -> bool:
    sections = route.get("sections")
    return isinstance(sections, list) and any(
        isinstance(section, dict) and section.get("type") == "transit"
        for section in sections
    )


def _scheduled_duration(sections: list[Any]) -> int | None:
    first = sections[0] if isinstance(sections[0], dict) else {}
    last = sections[-1] if isinstance(sections[-1], dict) else {}
    departure = first.get("departure")
    arrival = last.get("arrival")
    if not isinstance(departure, dict) or not isinstance(arrival, dict):
        return None
    start = _parse_datetime(departure.get("time"))
    end = _parse_datetime(arrival.get("time"))
    if start is None or end is None or end <= start:
        return None
    return int((end - start).total_seconds())


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_coordinate(coordinate: tuple[float, float]) -> str:
    return f"{coordinate[0]:.7f},{coordinate[1]:.7f}"


def _non_negative_int(value: Any) -> int:
    parsed = int(value)
    if parsed < 0:
        raise ValueError("HERE transit summary values cannot be negative.")
    return parsed
