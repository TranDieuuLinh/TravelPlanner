from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.modules.itinerary_planner.contract import PlannerContractModel


class DirectionsOrigin(PlannerContractModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=300)


class DirectionsDestination(DirectionsOrigin):
    item_id: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=1000)
    selected: bool = True
    time_window: str | None = Field(default=None, max_length=200)


class CurrentLocationRouteRequest(PlannerContractModel):
    origin: DirectionsOrigin
    destination: DirectionsDestination
    departure_time: str | None = Field(default=None, max_length=100)
    preferred_modes: list[str] = Field(default_factory=list, max_length=5)
    avoid_modes: list[str] = Field(default_factory=list, max_length=5)


class DayDirectionsRequest(PlannerContractModel):
    origin: DirectionsOrigin
    destinations: list[DirectionsDestination] = Field(min_length=1, max_length=30)
    requested_mode: Literal["walk", "car", "bus"] | None = None
    departure_time: str | None = Field(default=None, max_length=100)


class DirectionsResponseLeg(PlannerContractModel):
    mode: str
    distance_meters: int = Field(ge=0)
    estimated_duration_minutes: int = Field(ge=0)
    geometry_coordinates: list[tuple[float, float]] = Field(min_length=2)
    source: str
    verified: bool
    from_item_id: str | None = None
    to_item_id: str | None = None
    from_place: str
    to_place: str
