from __future__ import annotations

from app.modules.place_checker.output_contract import PlannerOutputEntertainment
from app.shared.tools.bayesian_rating import bayesian_prior, bayesian_rating
from app.shared.tools.search_places.normalization import normalize_text


HIGH_BAYESIAN_RATING = 4.2
DAYTIME_START_MINUTE = 7 * 60
DAYTIME_END_MINUTE = 18 * 60
EVENING_START_MINUTE = 18 * 60
EVENING_END_MINUTE = 24 * 60
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
    drink_dessert_limit: int | None = None,
) -> list[PlannerOutputEntertainment]:
    """Fill independent evening and daytime pools, then return one JSON list."""
    drink_dessert_limit = drink_dessert_limit or max(3, days * 3)
    required = [candidate for candidate in candidates if _is_required(candidate)]
    optional = [candidate for candidate in candidates if not _is_required(candidate)]
    required_entertainment = sum(
        candidate.entity_type == "entertainment" for candidate in required
    )
    required_drinks = sum(
        candidate.entity_type == "drink_dessert" for candidate in required
    )
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
    eligible_entertainment = [
        candidate
        for candidate in optional_entertainment
        if (
            (adjusted.get(candidate.place_id) or 0) >= HIGH_BAYESIAN_RATING
            and _is_tourist_entertainment(candidate)
            and _overlaps(candidate, EVENING_START_MINUTE, EVENING_END_MINUTE)
        )
    ]
    eligible_entertainment.sort(
        key=lambda candidate: (
            -(adjusted.get(candidate.place_id) or candidate.rating or 0),
            -(candidate.review_count or 0),
            candidate.place_id,
        )
    )
    eligible_drinks = sorted(
        (
            candidate
            for candidate in optional
            if candidate.entity_type == "drink_dessert"
            and _is_tourist_drink_dessert(candidate)
            and _overlaps(candidate, DAYTIME_START_MINUTE, DAYTIME_END_MINUTE)
        ),
        key=lambda candidate: (
            -(candidate.rating or 0),
            -(candidate.review_count or 0),
            candidate.place_id,
        ),
    )
    selected = [
        *required,
        *eligible_entertainment[: max(0, limit - required_entertainment)],
        *eligible_drinks[: max(0, drink_dessert_limit - required_drinks)],
    ]
    unique: list[PlannerOutputEntertainment] = []
    seen: set[str] = set()
    for candidate in selected:
        if candidate.place_id in seen:
            continue
        seen.add(candidate.place_id)
        unique.append(candidate)
    return unique


def _windows(candidate: PlannerOutputEntertainment):
    if candidate.preferred_time_windows:
        return candidate.preferred_time_windows
    return [
        window
        for windows in (candidate.opening_hours or {}).values()
        for window in windows
    ]


def _overlaps(
    candidate: PlannerOutputEntertainment,
    start_minute: int,
    end_minute: int,
) -> bool:
    return any(
        window.start_minute < end_minute and window.end_minute > start_minute
        for window in _windows(candidate)
    )


def _is_required(candidate: PlannerOutputEntertainment) -> bool:
    return candidate.priority in {"user_input", "url"}


def _is_tourist_entertainment(candidate: PlannerOutputEntertainment) -> bool:
    note = candidate.notes.text if candidate.notes is not None else ""
    identity = normalize_text(" ".join([candidate.name, note, *candidate.tags]))
    if NON_TOURIST_ENTERTAINMENT_TOKENS & set(identity.split()):
        return False
    return not any(marker in identity for marker in NON_TOURIST_ENTERTAINMENT_MARKERS)


def _is_tourist_drink_dessert(candidate: PlannerOutputEntertainment) -> bool:
    note = candidate.notes.text if candidate.notes is not None else ""
    identity = normalize_text(" ".join([candidate.name, note, *candidate.tags]))
    padded = f" {identity} "
    return any(f" {marker} " in padded for marker in DRINK_DESSERT_MARKERS)
