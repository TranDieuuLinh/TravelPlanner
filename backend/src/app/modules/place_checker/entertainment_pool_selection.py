from __future__ import annotations

from app.modules.place_checker.output_contract import PlannerOutputEntertainment
from app.shared.tools.bayesian_rating import bayesian_prior, bayesian_rating
from app.shared.tools.search_places.normalization import normalize_text


HIGH_BAYESIAN_RATING = 4.2
MORNING_END_MINUTE = 12 * 60
NON_TOURIST_ENTERTAINMENT_MARKERS = (
    "art supply store",
    "art school",
    "artistic handicrafts",
    "ceramic shop",
    "clothing store",
    "event planner",
    "gift shop",
    "souvenir store",
    "thuoc danh muc store",
    "cho thue trang phuc",
    "may do vest",
    "music academy",
    "music school",
    "music talent",
    "photo booth",
    "trung tam am nhac",
    "yoga studio",
)
NON_TOURIST_ENTERTAINMENT_TOKENS = frozenset({"service", "shop", "store"})
DRINK_DESSERT_MARKERS = (
    "bakery",
    "bar",
    "ca phe",
    "cafe",
    "coffee",
    "dessert",
    "ice cream",
    "juice",
    "lounge",
    "nuoc ep",
    "patisserie",
    "pub",
    "tea",
    "tra",
)


def select_entertainment_pool(
    candidates: list[PlannerOutputEntertainment],
    *,
    days: int,
    limit: int,
) -> list[PlannerOutputEntertainment]:
    """Keep evening-capable options and at most one morning-only item per day."""
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
        if (
            candidate.entity_type == "drink_dessert"
            and _is_tourist_drink_dessert(candidate)
        )
        or (
            (adjusted.get(candidate.place_id) or 0) >= HIGH_BAYESIAN_RATING
            and _is_tourist_entertainment(candidate)
        )
    ]
    eligible_optional.sort(
        key=lambda candidate: (
            1 if _is_morning_only(candidate) else 0,
            -(adjusted.get(candidate.place_id) or candidate.rating or 0),
            -(candidate.review_count or 0),
        )
    )

    selected = list(required)
    morning_cap = max(1, days)
    optional_morning_count = 0
    for candidate in eligible_optional:
        if len(selected) >= max(limit, len(required)):
            break
        is_optional_morning_entertainment = (
            candidate.entity_type == "entertainment"
            and _is_morning_only(candidate)
        )
        if is_optional_morning_entertainment:
            if optional_morning_count >= morning_cap:
                continue
            optional_morning_count += 1
        selected.append(candidate)
    return selected


def _is_required(candidate: PlannerOutputEntertainment) -> bool:
    return candidate.priority in {"user_input", "url"}


def _is_tourist_entertainment(candidate: PlannerOutputEntertainment) -> bool:
    note = candidate.notes.text if candidate.notes is not None else ""
    identity = normalize_text(" ".join([candidate.name, note, *candidate.tags]))
    if NON_TOURIST_ENTERTAINMENT_TOKENS & set(identity.split()):
        return False
    return not any(
        marker in identity for marker in NON_TOURIST_ENTERTAINMENT_MARKERS
    )


def _is_tourist_drink_dessert(candidate: PlannerOutputEntertainment) -> bool:
    note = candidate.notes.text if candidate.notes is not None else ""
    identity = normalize_text(" ".join([candidate.name, note, *candidate.tags]))
    padded = f" {identity} "
    return any(f" {marker} " in padded for marker in DRINK_DESSERT_MARKERS)


def _is_morning_only(candidate: PlannerOutputEntertainment) -> bool:
    if candidate.preferred_time_windows:
        return all(
            window.end_minute <= MORNING_END_MINUTE
            for window in candidate.preferred_time_windows
        )
    if not candidate.opening_hours:
        return False
    windows = [
        window
        for windows in candidate.opening_hours.values()
        for window in windows
    ]
    return bool(windows) and all(
        window.end_minute <= MORNING_END_MINUTE for window in windows
    )
