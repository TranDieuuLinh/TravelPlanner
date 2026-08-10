from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from app.modules.plans.place_selector.timeline_policy import DAILY_ACTIVITY_MINUTES
from app.modules.plans.routing.provider import TravelTimeMatrixProvider
from app.modules.plans.solver.contracts import (
    CandidatePool,
    MatrixSnapshot,
    PlanningCandidate,
    PlanningDayAllocation,
    PlanningSolution,
)


DEFAULT_TRANSFER_SECONDS = 15 * 60
MAX_TRIP_DAYS = 30
MEALS_PER_DAY = 3


class ClusterFirstRepairSolver:
    """Deterministic mandatory-first geographic allocation.

    V1 deliberately uses bounded greedy insertion plus a small repair pass. It
    selects the day count and allocation in memory, without LLM calls or full
    planner retries. Optional candidates can use the same contract later.
    """

    def solve(
        self,
        pool: CandidatePool,
        *,
        requested_days: int,
        days_locked: bool,
        matrix_provider: TravelTimeMatrixProvider | None = None,
    ) -> PlanningSolution:
        matrix = self._build_matrix(pool, matrix_provider)
        candidates = sorted(
            pool.candidates,
            key=lambda candidate: (
                not candidate.mandatory,
                candidate.source_order or 10_000,
                candidate.candidate_id,
            ),
        )
        day_count = max(1, min(MAX_TRIP_DAYS, requested_days))
        days: list[list[PlanningCandidate]] = [[] for _ in range(day_count)]
        unscheduled: list[str] = []

        for candidate in candidates:
            day_index = self._best_day(candidate, days, matrix)
            if day_index is None and not days_locked and len(days) < MAX_TRIP_DAYS:
                days.append([])
                day_index = len(days) - 1
            if day_index is None:
                unscheduled.append(candidate.candidate_id)
                continue
            days[day_index].append(candidate)

        self._repair(days, matrix)
        ordered_days = [self._nearest_neighbor(day, matrix) for day in days]
        return PlanningSolution(
            days=tuple(
                PlanningDayAllocation(
                    day=index + 1,
                    candidate_ids=tuple(item.candidate_id for item in day),
                )
                for index, day in enumerate(ordered_days)
            ),
            unscheduled_candidate_ids=tuple(unscheduled),
            matrix=matrix,
        )

    def _best_day(
        self,
        candidate: PlanningCandidate,
        days: list[list[PlanningCandidate]],
        matrix: MatrixSnapshot,
    ) -> int | None:
        feasible: list[tuple[float, int, int]] = []
        for index, day in enumerate(days):
            if not self._fits(candidate, day, matrix):
                continue
            # Geographic insertion remains the primary signal. When route
            # costs tie (especially with the missing-coordinate fallback),
            # balance occupied minutes instead of filling day one to its hard
            # limit before considering day two.
            occupied_minutes = sum(
                item.duration_minutes for item in day if item.kind == candidate.kind
            )
            feasible.append(
                (
                    self._insertion_cost(candidate, day, matrix),
                    occupied_minutes,
                    index,
                )
            )
        return min(feasible)[2] if feasible else None

    def _fits(
        self,
        candidate: PlanningCandidate,
        day: list[PlanningCandidate],
        matrix: MatrixSnapshot,
    ) -> bool:
        if candidate.kind == "meal":
            return sum(item.kind == "meal" for item in day) < MEALS_PER_DAY
        activities = [item for item in day if item.kind == "activity"]
        used = sum(item.duration_minutes for item in activities)
        travel = self._path_seconds(activities, matrix) / 60
        added_travel = self._insertion_cost(candidate, activities, matrix) / 60
        return used + candidate.duration_minutes + travel + added_travel <= DAILY_ACTIVITY_MINUTES

    @staticmethod
    def _insertion_cost(
        candidate: PlanningCandidate,
        day: list[PlanningCandidate],
        matrix: MatrixSnapshot,
    ) -> float:
        located = [item for item in day if item.candidate_id != candidate.candidate_id]
        if not located:
            return 0.0
        return min(
            matrix.seconds(item.candidate_id, candidate.candidate_id)
            for item in located
        )

    @staticmethod
    def _path_seconds(
        day: list[PlanningCandidate],
        matrix: MatrixSnapshot,
    ) -> float:
        return sum(
            matrix.seconds(left.candidate_id, right.candidate_id)
            for left, right in zip(day, day[1:])
        )

    def _repair(
        self,
        days: list[list[PlanningCandidate]],
        matrix: MatrixSnapshot,
    ) -> None:
        """One bounded move pass improves obviously expensive assignments."""

        for source_index, source in enumerate(days):
            for candidate in list(source):
                current_cost = self._insertion_cost(candidate, source, matrix)
                alternatives = [
                    (self._insertion_cost(candidate, target, matrix), target_index)
                    for target_index, target in enumerate(days)
                    if target_index != source_index
                    and self._fits(candidate, target, matrix)
                ]
                if not alternatives:
                    continue
                best_cost, target_index = min(alternatives)
                if best_cost + 60 < current_cost:
                    source.remove(candidate)
                    days[target_index].append(candidate)

    def _nearest_neighbor(
        self,
        day: list[PlanningCandidate],
        matrix: MatrixSnapshot,
    ) -> list[PlanningCandidate]:
        if len(day) < 2:
            return list(day)
        remaining = list(day)
        ordered = [remaining.pop(0)]
        while remaining:
            current = ordered[-1]
            next_item = min(
                remaining,
                key=lambda item: (
                    matrix.seconds(current.candidate_id, item.candidate_id),
                    item.candidate_id,
                ),
            )
            remaining.remove(next_item)
            ordered.append(next_item)
        return ordered

    def _build_matrix(
        self,
        pool: CandidatePool,
        provider: TravelTimeMatrixProvider | None,
    ) -> MatrixSnapshot:
        candidates = list(pool.candidates)
        candidate_ids = tuple(item.candidate_id for item in candidates)
        all_located = all(
            item.latitude is not None and item.longitude is not None
            for item in candidates
        )
        if provider is not None and candidates and all_located:
            result = provider.calculate(
                [(item.latitude, item.longitude) for item in candidates],
                transport_mode="car",
                departure_time=None,
            )
            if result is not None and self._valid_matrix(
                result.travel_times_seconds,
                len(candidates),
            ):
                return MatrixSnapshot(
                    candidate_ids=candidate_ids,
                    travel_times_seconds=tuple(
                        tuple(
                            float(value) if value is not None else DEFAULT_TRANSFER_SECONDS
                            for value in row
                        )
                        for row in result.travel_times_seconds
                    ),
                    provider=result.provider,
                )

        rows: list[tuple[float, ...]] = []
        for origin in candidates:
            row: list[float] = []
            for destination in candidates:
                if origin.candidate_id == destination.candidate_id:
                    row.append(0.0)
                elif (
                    origin.latitude is None
                    or origin.longitude is None
                    or destination.latitude is None
                    or destination.longitude is None
                ):
                    row.append(DEFAULT_TRANSFER_SECONDS)
                else:
                    meters = _haversine_meters(
                        (origin.latitude, origin.longitude),
                        (destination.latitude, destination.longitude),
                    )
                    row.append(max(5 * 60, meters / 35000 * 3600))
            rows.append(tuple(row))
        return MatrixSnapshot(
            candidate_ids=candidate_ids,
            travel_times_seconds=tuple(rows),
            provider="geodesic_estimate",
        )

    @staticmethod
    def _valid_matrix(matrix: list[list[int | None]], size: int) -> bool:
        return len(matrix) == size and all(len(row) == size for row in matrix)


def _haversine_meters(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> float:
    latitude_1, longitude_1 = map(radians, origin)
    latitude_2, longitude_2 = map(radians, destination)
    delta_latitude = latitude_2 - latitude_1
    delta_longitude = longitude_2 - longitude_1
    value = (
        sin(delta_latitude / 2) ** 2
        + cos(latitude_1) * cos(latitude_2) * sin(delta_longitude / 2) ** 2
    )
    return 6_371_000 * 2 * asin(sqrt(value))
