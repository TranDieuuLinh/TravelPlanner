from __future__ import annotations

from typing import Protocol

from app.modules.itinerary_planner.ports import (
    RouteDetailProvider,
    RoutingMatrixProvider,
)
from app.modules.itinerary_planner.routing_models import (
    MatrixLocation,
    RouteLegRequest,
    RouteDetail,
    RoutingPhaseError,
    TravelMatrix,
)


class RoutingAdapter(RoutingMatrixProvider, RouteDetailProvider, Protocol):
    pass


class FallbackRoutingAdapter:
    """Try the primary provider first, then use an approximate provider."""

    def __init__(
        self,
        primary: RoutingAdapter,
        fallback: RoutingAdapter,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    async def matrix(
        self,
        locations: tuple[MatrixLocation, ...],
        profile: str,
    ) -> TravelMatrix:
        try:
            return await self.primary.matrix(locations, profile)
        except RoutingPhaseError:
            return await self.fallback.matrix(locations, profile)

    async def route(
        self,
        legs: tuple[RouteLegRequest, ...],
        profile: str,
    ) -> tuple[RouteDetail, ...]:
        try:
            return await self.primary.route(legs, profile)
        except RoutingPhaseError:
            return await self.fallback.route(legs, profile)
