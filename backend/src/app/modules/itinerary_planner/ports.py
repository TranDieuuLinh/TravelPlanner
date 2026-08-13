from __future__ import annotations

from typing import Protocol

from app.modules.itinerary_planner.routing_models import (
    MatrixLocation,
    RouteDetail,
    RouteLegRequest,
    TravelMatrix,
)


class RoutingMatrixProvider(Protocol):
    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix: ...


class RouteDetailProvider(Protocol):
    async def route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]: ...


class TransportCostEstimator(Protocol):
    def estimate(
        self,
        distance_meters: int,
        profile: str,
        people: int,
    ) -> tuple[int, int]:
        """Return (daytime cost, late-night surcharge), both per person."""
        ...


class MatrixCache(Protocol):
    async def get(self, key: str) -> TravelMatrix | None: ...

    async def put(self, key: str, matrix: TravelMatrix) -> None: ...
