from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    PlannerCandidate,
)
from app.modules.itinerary_planner.quality import bayesian_quality_by_id

ACTIVITY_RESERVE_PER_DAY = 14
MIN_ACTIVITY_SEPARATORS_PER_DAY = 2
MAX_OPTIONAL_DAYS = 2
KNN_NEIGHBORS = 10
CENTER_DENSITY_WEIGHT = 0.7
CENTER_QUALITY_WEIGHT = 0.3
PRIORITY_VALUES = {CandidatePriority.user_input, CandidatePriority.url}


@dataclass(frozen=True, slots=True)
class ActivityDayProjection:
    preferred_days: dict[str, frozenset[int]]
    center_by_day: dict[int, PlannerCandidate]


def project_activity_days(
    *,
    days: int,
    places: list[PlannerCandidate],
    feasible_days: dict[str, frozenset[int]],
) -> ActivityDayProjection:
    """Build fast geographic preferences while retaining all feasible reserve days."""
    target = max(
        MIN_ACTIVITY_SEPARATORS_PER_DAY,
        min(ACTIVITY_RESERVE_PER_DAY, len(places) // days),
    )
    centers = _select_dense_centers(places, days)
    center_by_day = {day: center for day, center in enumerate(centers, 1)}
    preferred = _assign_nearest_days(
        places,
        feasible_days,
        center_by_day,
        target,
    )
    _rebalance_once(places, feasible_days, preferred, center_by_day, target)
    return ActivityDayProjection(preferred, center_by_day)


def _select_dense_centers(
    places: list[PlannerCandidate],
    count: int,
) -> list[PlannerCandidate]:
    ordered = sorted(places, key=lambda item: item.place_id)
    quality = bayesian_quality_by_id(ordered)
    density = _normalized_knn_density(ordered)
    density_floor = sorted(density.values())[len(density) // 4]
    dense = [
        candidate
        for candidate in ordered
        if density[candidate.place_id] >= density_floor
    ]
    candidates = dense if len(dense) >= count else ordered
    first = min(
        candidates,
        key=lambda item: (
            -_center_score(item, density, quality),
            sum(_distance_km(item, other) for other in ordered),
            item.place_id,
        ),
    )
    centers = [first]
    remaining = [item for item in candidates if item.place_id != first.place_id]
    while remaining and len(centers) < count:
        selected = min(
            remaining,
            key=lambda item: (
                -min(_distance_km(item, center) for center in centers),
                -_center_score(item, density, quality),
                item.place_id,
            ),
        )
        centers.append(selected)
        remaining.remove(selected)
    return centers


def _center_score(
    candidate: PlannerCandidate,
    density: dict[str, float],
    quality: dict[str, float],
) -> int:
    return round(
        (
            CENTER_DENSITY_WEIGHT * density[candidate.place_id]
            + CENTER_QUALITY_WEIGHT * quality[candidate.place_id]
        )
        * 1_000_000
    )


def _normalized_knn_density(
    places: list[PlannerCandidate],
) -> dict[str, float]:
    if len(places) <= 1:
        return {candidate.place_id: 1.0 for candidate in places}
    neighbor_count = min(KNN_NEIGHBORS, len(places) - 1)
    raw = {}
    for candidate in places:
        nearest = sorted(
            _distance_km(candidate, other)
            for other in places
            if other.place_id != candidate.place_id
        )[:neighbor_count]
        mean_distance = sum(nearest) / neighbor_count
        raw[candidate.place_id] = 1 / max(mean_distance, 0.001)
    minimum = min(raw.values())
    maximum = max(raw.values())
    if maximum == minimum:
        return {candidate_id: 1.0 for candidate_id in raw}
    return {
        candidate_id: (value - minimum) / (maximum - minimum)
        for candidate_id, value in raw.items()
    }


def _assign_nearest_days(
    places: list[PlannerCandidate],
    feasible_days: dict[str, frozenset[int]],
    center_by_day: dict[int, PlannerCandidate],
    target: int,
) -> dict[str, frozenset[int]]:
    preferred = {
        candidate.place_id: feasible_days[candidate.place_id]
        for candidate in places
        if candidate.priority in PRIORITY_VALUES
    }
    counts = {
        day: sum(day in selected for selected in preferred.values())
        for day in center_by_day
    }
    optional = sorted(
        (item for item in places if item.priority not in PRIORITY_VALUES),
        key=lambda item: (len(feasible_days[item.place_id]), item.place_id),
    )
    for candidate in optional:
        allowed = feasible_days[candidate.place_id]
        under_target = [
            day
            for day in allowed
            if day in center_by_day and counts[day] < target
        ]
        choices = under_target or [day for day in allowed if day in center_by_day]
        nearest = min(
            choices,
            key=lambda day: (
                _distance_km(candidate, center_by_day[day]),
                day,
            ),
        )
        preferred[candidate.place_id] = frozenset({nearest})
        counts[nearest] += 1
    return preferred


def _rebalance_once(
    places: list[PlannerCandidate],
    feasible_days: dict[str, frozenset[int]],
    preferred_days: dict[str, frozenset[int]],
    center_by_day: dict[int, PlannerCandidate],
    target: int,
) -> None:
    counts = {
        day: sum(day in preferred_days[item.place_id] for item in places)
        for day in center_by_day
    }
    for day in sorted(center_by_day, key=lambda value: (counts[value], value)):
        needed = max(0, target - counts[day])
        options = sorted(
            (
                candidate
                for candidate in places
                if candidate.priority not in PRIORITY_VALUES
                and day in feasible_days[candidate.place_id]
                and day not in preferred_days[candidate.place_id]
                and len(preferred_days[candidate.place_id]) < MAX_OPTIONAL_DAYS
            ),
            key=lambda item: (
                _distance_km(item, center_by_day[day])
                - min(
                    _distance_km(item, center_by_day[assigned])
                    for assigned in preferred_days[item.place_id]
                ),
                item.place_id,
            ),
        )
        for candidate in options[:needed]:
            preferred_days[candidate.place_id] = frozenset(
                {*preferred_days[candidate.place_id], day}
            )
            counts[day] += 1


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
