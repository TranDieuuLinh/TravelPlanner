from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.modules.plans.routing.provider import (
    RouteTransportMode,
    TravelTimeMatrix,
)


class ValhallaTravelTimeMatrixProvider:
    provider_name = "valhalla_matrix"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def calculate(
        self,
        coordinates: list[tuple[float, float]],
        *,
        transport_mode: RouteTransportMode,
        departure_time: datetime | None,
    ) -> TravelTimeMatrix | None:
        if not coordinates:
            return None
        locations = [
            {"lat": latitude, "lon": longitude}
            for latitude, longitude in coordinates
        ]
        body: dict[str, Any] = {
            "sources": locations,
            "targets": locations,
            "costing": (
                "pedestrian"
                if transport_mode == "pedestrian"
                else "auto"
            ),
            "verbose": False,
        }
        if departure_time is not None:
            body["date_time"] = {
                "type": 3,
                "value": departure_time.strftime("%Y-%m-%dT%H:%M"),
            }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/sources_to_targets",
                    json=body,
                )
            response.raise_for_status()
            matrix = _parse_matrix(
                response.json(),
                expected_size=len(coordinates),
            )
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            return None
        return TravelTimeMatrix(
            travel_times_seconds=matrix,
            provider=self.provider_name,
            fetched_at=datetime.now(timezone.utc),
        )


def _parse_matrix(
    payload: Any,
    *,
    expected_size: int,
) -> list[list[int | None]]:
    if not isinstance(payload, dict):
        raise ValueError("Valhalla matrix response must be an object.")
    result = payload.get("sources_to_targets")
    if not isinstance(result, dict):
        raise ValueError("Valhalla concise matrix response is missing.")
    durations = result.get("durations")
    if (
        not isinstance(durations, list)
        or len(durations) != expected_size
        or any(
            not isinstance(row, list) or len(row) != expected_size
            for row in durations
        )
    ):
        raise ValueError("Valhalla matrix dimensions do not match inputs.")
    return [
        [_duration(value) for value in row]
        for row in durations
    ]


def _duration(value: Any) -> int | None:
    if value is None:
        return None
    parsed = round(float(value))
    if parsed < 0:
        raise ValueError("Valhalla matrix duration cannot be negative.")
    return parsed
