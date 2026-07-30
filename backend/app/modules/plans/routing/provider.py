from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol


RouteTransportMode = Literal["pedestrian", "car"]


@dataclass(frozen=True)
class RouteCalculation:
    distance_meters: int
    duration_seconds: int
    geometry_coordinates: list[tuple[float, float]]
    provider: str
    fetched_at: datetime
    details: dict[str, Any] = field(default_factory=dict)


class RouteProvider(Protocol):
    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        transport_mode: RouteTransportMode,
    ) -> RouteCalculation | None: ...


class TransitRouteProvider(Protocol):
    def calculate(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        *,
        departure_time: datetime | None,
        modes: tuple[str, ...] = (),
    ) -> RouteCalculation | None: ...
