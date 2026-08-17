from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias


class RoutingErrorCode(StrEnum):
    matrix_timeout = "matrix_timeout"
    matrix_provider_error = "matrix_provider_error"
    matrix_invalid_response = "matrix_invalid_response"
    matrix_provider_not_configured = "matrix_provider_not_configured"
    transport_cost_not_configured = "transport_cost_not_configured"
    unreachable_priority = "unreachable_priority"


STRAIGHT_LINE_PROVIDER = "straight_line_fallback"
STRAIGHT_LINE_WARNING = (
    "Valhalla unavailable; straight-line routing fallback is approximate and "
    "does not represent road distance."
)


class RoutingPhaseError(RuntimeError):
    def __init__(self, code: RoutingErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class MatrixLocation:
    node_id: str
    latitude: float
    longitude: float
    canonical_key: str


@dataclass(frozen=True, slots=True)
class MatrixCell:
    duration_seconds: float | None
    distance_meters: float | None
    reachable: bool
    # Derived after PlaceChecker candidates are normalized.  Providers do not
    # need to know application-level venue types.
    food_to_food: bool = False


@dataclass(frozen=True, slots=True)
class TravelMatrix:
    node_ids: tuple[str, ...]
    cells: tuple[tuple[MatrixCell, ...], ...]
    profile: str
    provider: str
    provider_version: str
    cache_key: str | None = None

    def cell(self, origin_node_id: str, destination_node_id: str) -> MatrixCell:
        origin = self.node_ids.index(origin_node_id)
        destination = self.node_ids.index(destination_node_id)
        return self.cells[origin][destination]


@dataclass(frozen=True, slots=True)
class RouteLegRequest:
    origin: MatrixLocation
    destination: MatrixLocation


@dataclass(frozen=True, slots=True)
class RouteDetail:
    origin_node_id: str
    destination_node_id: str
    duration_seconds: float
    distance_meters: float
    encoded_polyline: str | None
    provider: str


@dataclass(frozen=True, slots=True)
class SafeTravel:
    raw_minutes: int
    safe_minutes: int
    distance_meters: int
    transport_cost_per_person: int
    late_night_surcharge_per_person: int = 0


@dataclass(frozen=True, slots=True)
class SparseArc:
    origin_id: str
    destination_id: str
    feasible_days: frozenset[int]
    travel: SafeTravel
    forced_reasons: frozenset[str] = frozenset()

    @property
    def is_virtual(self) -> bool:
        return self.origin_id.startswith("__") or self.destination_id.startswith("__")


CandidatePair: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True)
class RoutingProblem:
    locations: tuple[MatrixLocation, ...]
    candidate_to_matrix_node: dict[str, str]
    matrix_node_to_candidates: dict[str, tuple[str, ...]]
    matrix: TravelMatrix
    travel_by_candidate_pair: dict[CandidatePair, SafeTravel]
    sparse_arcs: tuple[SparseArc, ...]
    neighbor_limit: int
    warnings: tuple[str, ...]
