from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.modules.plans.routing.provider import TravelTimeMatrixProvider


CandidateKind = Literal["activity", "meal"]
CandidatePriorityTier = Literal[0, 1, 2, 3]

USER_INTENT_TIER: CandidatePriorityTier = 0
URL_SOURCE_TIER: CandidatePriorityTier = 1
REQUIRED_EXPERIENCE_TIER: CandidatePriorityTier = 2
OPTIONAL_SUGGESTION_TIER: CandidatePriorityTier = 3


@dataclass(frozen=True)
class PlanningCandidate:
    """Hydrated, deterministic input to the planning solver."""

    candidate_id: str
    name: str
    kind: CandidateKind
    duration_minutes: int
    mandatory: bool
    latitude: float | None = None
    longitude: float | None = None
    source_order: int | None = None
    source_day: int | None = None
    priority_tier: CandidatePriorityTier = USER_INTENT_TIER


@dataclass(frozen=True)
class CandidatePool:
    candidates: tuple[PlanningCandidate, ...]


@dataclass(frozen=True)
class MatrixSnapshot:
    """One reusable candidate matrix; indices are stable candidate identities."""

    candidate_ids: tuple[str, ...]
    travel_times_seconds: tuple[tuple[float, ...], ...]
    provider: str

    def seconds(self, origin_id: str, destination_id: str) -> float:
        if origin_id == destination_id:
            return 0.0
        try:
            origin = self.candidate_ids.index(origin_id)
            destination = self.candidate_ids.index(destination_id)
        except ValueError:
            return 15 * 60
        return self.travel_times_seconds[origin][destination]


@dataclass(frozen=True)
class PlanningDayAllocation:
    day: int
    candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class PlanningSolution:
    days: tuple[PlanningDayAllocation, ...]
    unscheduled_candidate_ids: tuple[str, ...]
    matrix: MatrixSnapshot

    @property
    def day_count(self) -> int:
        return len(self.days)

    @property
    def candidate_day(self) -> dict[str, int]:
        return {
            candidate_id: day.day
            for day in self.days
            for candidate_id in day.candidate_ids
        }


class PlanningSolver(Protocol):
    def solve(
        self,
        pool: CandidatePool,
        *,
        requested_days: int,
        days_locked: bool,
        matrix_provider: TravelTimeMatrixProvider | None = None,
    ) -> PlanningSolution: ...
