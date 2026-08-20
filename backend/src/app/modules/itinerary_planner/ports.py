from __future__ import annotations

from typing import Protocol

from app.modules.itinerary_planner.routing_models import (
    MatrixCell,
    MatrixLocation,
    RouteDetail,
    RouteLegRequest,
    TravelMatrix,
)

MatrixCellCacheKey = tuple[str, str, str, str]


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


class MatrixCache(Protocol):
    async def get(self, key: str) -> TravelMatrix | None: ...

    async def put(self, key: str, matrix: TravelMatrix) -> None: ...


class MatrixCellCache(Protocol):
    async def get_many(
        self, keys: tuple[MatrixCellCacheKey, ...]
    ) -> dict[MatrixCellCacheKey, MatrixCell]: ...

    async def put_many(
        self, values: dict[MatrixCellCacheKey, MatrixCell]
    ) -> None: ...
