from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    PlannerCandidate,
)

ACTIVITY_RESERVE_PER_DAY = 14
MIN_ACTIVITY_SEPARATORS_PER_DAY = 2
MAX_OPTIONAL_DAYS = 2
DENSE_CENTER_RADIUS_KM = 20.0
MEDOID_REFINEMENT_ROUNDS = 3
PRIORITY_VALUES = {CandidatePriority.user_input, CandidatePriority.url}


@dataclass(frozen=True, slots=True)
class ActivityDayProjection:
    feasible_days: dict[str, frozenset[int]]
    center_by_day: dict[int, PlannerCandidate]


def project_activity_days(
    *,
    days: int,
    places: list[PlannerCandidate],
    feasible_days: dict[str, frozenset[int]],
) -> ActivityDayProjection:
    """Build geographically compact day domains with a daily reserve floor."""
    target = max(
        MIN_ACTIVITY_SEPARATORS_PER_DAY,
        min(ACTIVITY_RESERVE_PER_DAY, len(places) // days),
    )
    centers = _select_dense_centers(places, days, target)
    center_by_day = {day: center for day, center in enumerate(centers, 1)}
    projected = dict(feasible_days)

    for _ in range(MEDOID_REFINEMENT_ROUNDS):
        assigned = _solve_balanced_assignment(
            days=days,
            places=places,
            feasible_days=feasible_days,
            center_by_day=center_by_day,
            target=target,
        )
        if assigned is None:
            return ActivityDayProjection(dict(feasible_days), center_by_day)
        projected.update(assigned)
        refined = _refine_medoids(places, projected, center_by_day)
        if all(
            refined[day].place_id == center_by_day[day].place_id
            for day in center_by_day
        ):
            break
        center_by_day = refined

    return ActivityDayProjection(projected, center_by_day)


def _select_dense_centers(
    places: list[PlannerCandidate],
    count: int,
    target: int,
) -> list[PlannerCandidate]:
    ordered = sorted(places, key=lambda item: item.place_id)
    dense = [
        candidate
        for candidate in ordered
        if sum(
            _distance_km(candidate, other) <= DENSE_CENTER_RADIUS_KM
            for other in ordered
        )
        >= max(1, target)
    ]
    candidates = dense if len(dense) >= count else ordered
    first = min(
        candidates,
        key=lambda item: (
            sum(_distance_km(item, other) for other in ordered),
            item.place_id,
        ),
    )
    centers = [first]
    remaining = [item for item in candidates if item.place_id != first.place_id]
    while remaining and len(centers) < count:
        selected = max(
            remaining,
            key=lambda item: (
                min(_distance_km(item, center) for center in centers),
                item.place_id,
            ),
        )
        centers.append(selected)
        remaining.remove(selected)
    return centers


def _solve_balanced_assignment(
    *,
    days: int,
    places: list[PlannerCandidate],
    feasible_days: dict[str, frozenset[int]],
    center_by_day: dict[int, PlannerCandidate],
    target: int,
) -> dict[str, frozenset[int]] | None:
    model = cp_model.CpModel()
    optional = [item for item in places if item.priority not in PRIORITY_VALUES]
    variables: dict[tuple[str, int], cp_model.IntVar] = {}
    for candidate in optional:
        allowed = sorted(feasible_days[candidate.place_id])
        choices = []
        for day in allowed:
            variable = model.NewBoolVar(f"activity_day:{candidate.place_id}:{day}")
            variables[(candidate.place_id, day)] = variable
            choices.append(variable)
        model.Add(sum(choices) >= 1)
        model.Add(sum(choices) <= min(MAX_OPTIONAL_DAYS, len(choices)))

    for day in range(1, days + 1):
        priority_count = sum(
            day in feasible_days[item.place_id]
            for item in places
            if item.priority in PRIORITY_VALUES
        )
        model.Add(
            priority_count
            + sum(
                variable
                for (candidate_id, candidate_day), variable in variables.items()
                if candidate_day == day
            )
            >= target
        )

    model.Minimize(
        sum(
            (1 + round(_distance_km(candidate, center_by_day[day]) * 1_000))
            * variables[(candidate.place_id, day)]
            for candidate in optional
            for day in feasible_days[candidate.place_id]
        )
    )
    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    projected = {
        candidate.place_id: (
            feasible_days[candidate.place_id]
            if candidate.priority in PRIORITY_VALUES
            else frozenset(
                day
                for day in feasible_days[candidate.place_id]
                if solver.Value(variables[(candidate.place_id, day)])
            )
        )
        for candidate in places
    }
    return projected


def _refine_medoids(
    places: list[PlannerCandidate],
    projected: dict[str, frozenset[int]],
    current: dict[int, PlannerCandidate],
) -> dict[int, PlannerCandidate]:
    result = dict(current)
    for day in current:
        members = [item for item in places if day in projected[item.place_id]]
        if not members:
            continue
        result[day] = min(
            members,
            key=lambda item: (
                sum(_distance_km(item, other) for other in members),
                item.place_id,
            ),
        )
    return result


def _distance_km(left: PlannerCandidate, right: PlannerCandidate) -> float:
    left_latitude = radians(left.coordinates.latitude)
    right_latitude = radians(right.coordinates.latitude)
    latitude_delta = right_latitude - left_latitude
    longitude_delta = radians(
        right.coordinates.longitude - left.coordinates.longitude
    )
    value = sin(latitude_delta / 2) ** 2 + (
        cos(left_latitude)
        * cos(right_latitude)
        * sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371.0 * asin(sqrt(value))
