from __future__ import annotations

from math import ceil

from app.modules.place_checker.output_contract import PlannerOutputEntertainment
from app.shared.tools.bayesian_rating import bayesian_prior, bayesian_rating


HIGH_BAYESIAN_RATING = 4.2
MORNING_START_MINUTE = 8 * 60
MORNING_END_MINUTE = 12 * 60


def select_entertainment_pool(
    candidates: list[PlannerOutputEntertainment],
    *,
    days: int,
    limit: int,
) -> list[PlannerOutputEntertainment]:
    """Keep required items and a small, high-quality optional morning reserve."""
    required = [candidate for candidate in candidates if _is_required(candidate)]
    optional = [candidate for candidate in candidates if not _is_required(candidate)]
    optional_entertainment = [
        candidate for candidate in optional if candidate.entity_type == "entertainment"
    ]
    prior = bayesian_prior(
        (candidate.rating, candidate.review_count)
        for candidate in optional_entertainment
    )
    adjusted = {
        candidate.place_id: bayesian_rating(
            rating=candidate.rating,
            review_count=candidate.review_count,
            prior_mean=prior.mean,
            prior_weight=prior.weight,
        )
        for candidate in optional_entertainment
    }
    eligible_optional = [
        candidate
        for candidate in optional
        if candidate.entity_type == "drink_dessert"
        or (adjusted.get(candidate.place_id) or 0) >= HIGH_BAYESIAN_RATING
    ]
    eligible_optional.sort(
        key=lambda candidate: (
            1 if _can_fit_morning(candidate) else 0,
            -(adjusted.get(candidate.place_id) or candidate.rating or 0),
            -(candidate.review_count or 0),
        )
    )

    selected = list(required)
    morning_cap = max(1, ceil(max(1, days) / 5))
    optional_morning_count = 0
    for candidate in eligible_optional:
        if len(selected) >= max(limit, len(required)):
            break
        is_optional_morning_entertainment = (
            candidate.entity_type == "entertainment"
            and _can_fit_morning(candidate)
        )
        if is_optional_morning_entertainment:
            if optional_morning_count >= morning_cap:
                continue
            optional_morning_count += 1
        selected.append(candidate)
    return selected


def _is_required(candidate: PlannerOutputEntertainment) -> bool:
    return candidate.priority in {"user_input", "url"}


def _can_fit_morning(candidate: PlannerOutputEntertainment) -> bool:
    if candidate.preferred_time_windows:
        return any(
            window.start_minute < MORNING_END_MINUTE
            and window.end_minute > MORNING_START_MINUTE
            for window in candidate.preferred_time_windows
        )
    if not candidate.opening_hours:
        return True
    return any(
        window.start_minute < MORNING_END_MINUTE
        and window.end_minute > MORNING_START_MINUTE
        for windows in candidate.opening_hours.values()
        for window in windows
    )
