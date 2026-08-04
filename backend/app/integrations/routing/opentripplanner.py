from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.integrations.routing.polyline import decode_polyline
from app.modules.plans.routing.provider import RouteCalculation
from app.modules.plans.routing.local_time import normalize_routing_datetime


_PLAN_QUERY = """
query Plan(
  $from: InputCoordinates!
  $to: InputCoordinates!
  $date: String!
  $time: String!
  $transportModes: [TransportMode]
) {
  plan(
    from: $from
    to: $to
    date: $date
    time: $time
    numItineraries: 3
    transportModes: $transportModes
  ) {
    itineraries {
        duration
      legs {
        mode
        transitLeg
        distance
        duration
        headsign
        realTime
        from { name }
        to { name }
        legGeometry { points }
        route { shortName longName }
        agency { name }
      }
    }
  }
}
"""

_BUS_MODES = {"BUS", "COACH", "TROLLEYBUS"}
_TRAIN_MODES = {
    "RAIL",
    "SUBWAY",
    "TRAM",
    "MONORAIL",
    "CABLE_CAR",
    "FUNICULAR",
}


class OpenTripPlannerTransitProvider:
    provider_name = "opentripplanner_transit"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 20.0,
        schedule_status: str = "current",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.schedule_status = schedule_status

    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        departure_time: datetime | None,
        modes: tuple[str, ...] = (),
    ) -> RouteCalculation | None:
        if departure_time is None:
            return None
        departure_time = normalize_routing_datetime(departure_time)
        variables = {
            "from": {"lat": origin[0], "lon": origin[1]},
            "to": {"lat": destination[0], "lon": destination[1]},
            "date": departure_time.date().isoformat(),
            "time": departure_time.time().replace(
                microsecond=0,
            ).isoformat(),
            "transportModes": [
                {"mode": "WALK"},
                {"mode": "TRANSIT"},
            ],
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    self.base_url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept-Language": "vi,en",
                    },
                    json={
                        "query": _PLAN_QUERY,
                        "operationName": "Plan",
                        "variables": variables,
                    },
                )
            response.raise_for_status()
            return _parse_plan(
                response.json(),
                provider=self.provider_name,
                requested_modes=modes,
                schedule_status=self.schedule_status,
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return None


def _parse_plan(
    payload: Any,
    *,
    provider: str,
    requested_modes: tuple[str, ...],
    schedule_status: str,
) -> RouteCalculation:
    if not isinstance(payload, dict) or payload.get("errors"):
        raise ValueError("OTP GraphQL returned an error.")
    data = payload.get("data")
    plan = data.get("plan") if isinstance(data, dict) else None
    itineraries = plan.get("itineraries") if isinstance(plan, dict) else None
    if not isinstance(itineraries, list):
        raise ValueError("OTP response contains no itineraries.")

    allowed, excluded = _mode_policy(requested_modes)
    candidates: list[tuple[int, dict[str, Any]]] = []
    for itinerary in itineraries:
        if not isinstance(itinerary, dict):
            continue
        legs = itinerary.get("legs")
        if not isinstance(legs, list):
            continue
        transit_modes = {
            str(leg.get("mode") or "").upper()
            for leg in legs
            if isinstance(leg, dict) and leg.get("transitLeg") is True
        }
        if not transit_modes:
            continue
        if allowed and not transit_modes.intersection(allowed):
            continue
        if excluded and transit_modes.intersection(excluded):
            continue
        candidates.append((_non_negative_int(itinerary.get("duration")), itinerary))
    if not candidates:
        raise ValueError("OTP returned no matching transit itinerary.")
    _, itinerary = min(candidates, key=lambda candidate: candidate[0])
    return _itinerary_calculation(
        itinerary,
        provider=provider,
        schedule_status=schedule_status,
    )


def _itinerary_calculation(
    itinerary: dict[str, Any],
    *,
    provider: str,
    schedule_status: str,
) -> RouteCalculation:
    legs = itinerary.get("legs")
    assert isinstance(legs, list)
    distance_meters = 0
    geometry: list[tuple[float, float]] = []
    transit_modes: list[str] = []
    lines: list[str] = []
    agencies: list[str] = []
    segments: list[dict[str, Any]] = []
    real_time = False
    for leg in legs:
        if not isinstance(leg, dict):
            raise ValueError("OTP itinerary leg must be an object.")
        distance_meters += round(_non_negative_float(leg.get("distance")))
        leg_geometry = leg.get("legGeometry")
        points = (
            leg_geometry.get("points")
            if isinstance(leg_geometry, dict)
            else None
        )
        if not isinstance(points, str) or not points:
            raise ValueError("OTP itinerary leg is missing geometry.")
        decoded = decode_polyline(points, precision=5)
        segment_geometry = decoded
        geometry_extension = decoded
        if geometry and decoded and geometry[-1] == decoded[0]:
            geometry_extension = decoded[1:]
        geometry.extend(geometry_extension)
        route = leg.get("route") if isinstance(leg.get("route"), dict) else {}
        line = route.get("shortName") or route.get("longName")
        from_place = (
            leg.get("from")
            if isinstance(leg.get("from"), dict)
            else {}
        )
        to_place = (
            leg.get("to")
            if isinstance(leg.get("to"), dict)
            else {}
        )
        segments.append(
            {
                "mode": str(leg.get("mode") or "").lower(),
                "fromPlace": str(from_place.get("name") or ""),
                "toPlace": str(to_place.get("name") or ""),
                "distanceMeters": round(
                    _non_negative_float(leg.get("distance"))
                ),
                "estimatedDurationMinutes": max(
                    1,
                    round(_non_negative_float(leg.get("duration")) / 60),
                ),
                "geometryCoordinates": segment_geometry,
                "line": line if isinstance(line, str) and line else None,
                "headsign": (
                    leg.get("headsign")
                    if isinstance(leg.get("headsign"), str)
                    else None
                ),
            }
        )
        if leg.get("transitLeg") is not True:
            continue
        mode = str(leg.get("mode") or "").lower()
        if mode and mode not in transit_modes:
            transit_modes.append(mode)
        if isinstance(line, str) and line and line not in lines:
            lines.append(line)
        agency = (
            leg.get("agency")
            if isinstance(leg.get("agency"), dict)
            else {}
        )
        agency_name = agency.get("name")
        if (
            isinstance(agency_name, str)
            and agency_name
            and agency_name not in agencies
        ):
            agencies.append(agency_name)
        real_time = real_time or leg.get("realTime") is True
    if len(geometry) < 2:
        raise ValueError("OTP route geometry must contain two points.")
    return RouteCalculation(
        distance_meters=distance_meters,
        duration_seconds=_non_negative_int(itinerary.get("duration")),
        geometry_coordinates=geometry,
        provider=provider,
        fetched_at=datetime.now(timezone.utc),
        details={
            "transitModes": transit_modes,
            "lines": lines,
            "agencies": agencies,
            "realTime": real_time,
            "scheduleStatus": schedule_status,
            "segments": segments,
        },
    )


def _mode_policy(
    requested_modes: tuple[str, ...],
) -> tuple[set[str], set[str]]:
    allowed: set[str] = set()
    excluded: set[str] = set()
    for mode in requested_modes:
        normalized = mode.casefold()
        target = excluded if normalized.startswith("-") else allowed
        normalized = normalized.removeprefix("-")
        if normalized == "bus":
            target.update(_BUS_MODES)
        elif normalized == "train":
            target.update(_TRAIN_MODES)
    return allowed, excluded


def _non_negative_float(value: Any) -> float:
    parsed = float(value)
    if parsed < 0:
        raise ValueError("OTP route value cannot be negative.")
    return parsed


def _non_negative_int(value: Any) -> int:
    return round(_non_negative_float(value))
