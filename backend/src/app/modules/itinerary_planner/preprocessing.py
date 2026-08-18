from __future__ import annotations

from math import ceil
from types import MappingProxyType

from app.modules.itinerary_planner.candidate_semantics import (
    eligibility_failure,
    normalize_candidate,
    normalize_tags,
    normalize_trip,
)
from app.modules.itinerary_planner.activity_time_policy import apply_activity_time_policy  # noqa: E501
from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    ItineraryPlannerInput,
    MealType,
    PlannerCandidate,
    PlannerEntertainmentCandidate,
    PlannerFoodCandidate,
    PlannerTrip,
)
from app.modules.itinerary_planner.day_domains import (
    MAX_OPTIONAL_DAYS,
    project_optional_day_domains,
)
from app.modules.itinerary_planner.policies import (
    LATE_NIGHT_TAGS,
    MEAL_POLICIES,
    OVERNIGHT_END_MINUTE,
    STANDARD_DAY_END_MINUTE,
)
from app.modules.itinerary_planner.preflight import validate_projected_pool
from app.modules.itinerary_planner.prepared_problem import (
    Candidate,
    CandidateDay,
    CandidateExclusion,
    MealSlot,
    MissingMealCoverage,
    PlanningPreflightError,
    PreparedPlanningProblem,
)
from app.modules.itinerary_planner.time_windows import (
    PlanningWindow,
    feasible_start_window,
    full_itinerary_window,
    normalize_and_merge,
    windows_fitting_duration,
)

PRIORITY_CANDIDATES = {CandidatePriority.user_input, CandidatePriority.url}


def _opening_windows(
    candidate: Candidate,
    day: int,
    latest_end_minute: int,
) -> tuple[tuple[PlanningWindow, ...], bool]:
    if candidate.opening_hours is None:
        return full_itinerary_window(latest_end_minute), True
    intervals = candidate.opening_hours.get(str(day))
    if intervals is None:
        return full_itinerary_window(latest_end_minute), True
    return normalize_and_merge(intervals, latest_end_minute), False


def is_late_night_eligible(candidate: Candidate) -> bool:
    return bool(set(normalize_tags(candidate.tags)) & LATE_NIGHT_TAGS)


def _exclusion(
    candidate: Candidate,
    reason_code: str,
    message: str,
) -> CandidateExclusion:
    return CandidateExclusion(
        place_id=candidate.place_id,
        name=candidate.name,
        priority=candidate.priority,
        reason_code=reason_code,
        message=message,
    )


def _store_exclusion(
    exclusion: CandidateExclusion,
    unscheduled: list[CandidateExclusion],
    discarded: list[CandidateExclusion],
) -> None:
    if exclusion.priority in PRIORITY_CANDIDATES:
        unscheduled.append(exclusion)
    else:
        discarded.append(exclusion)


def _prepare_place(
    candidate: PlannerCandidate,
    trip: PlannerTrip,
) -> tuple[
    PlannerCandidate,
    dict[int, tuple[PlanningWindow, ...]],
    frozenset[int],
    CandidateExclusion | None,
]:
    normalized = normalize_candidate(candidate)
    if failure := eligibility_failure(normalized, trip):
        return normalized, {}, frozenset(), _exclusion(normalized, *failure)
    if normalized.price.currency != trip.budget.currency:
        return (
            normalized,
            {},
            frozenset(),
            _exclusion(
                normalized,
                "currency_mismatch",
                "Candidate price currency does not match the trip budget currency.",
            ),
        )
    feasible: dict[int, tuple[PlanningWindow, ...]] = {}
    unknown_days: set[int] = set()
    had_open_window = False
    latest_end = (
        OVERNIGHT_END_MINUTE
        if is_late_night_eligible(normalized)
        else STANDARD_DAY_END_MINUTE
    )
    for day in range(1, trip.days + 1):
        opening, unknown = _opening_windows(normalized, day, latest_end)
        opening = apply_activity_time_policy(normalized, trip, day, opening)
        unknown_days.update({day} if unknown else set())
        had_open_window = had_open_window or bool(opening)
        fitting = windows_fitting_duration(opening, normalized.duration_minutes)
        if fitting:
            feasible[day] = fitting

    if feasible:
        return normalized, feasible, frozenset(unknown_days), None
    if not had_open_window:
        reason = "closed_for_entire_trip"
        message = "Candidate is closed for every trip day."
    else:
        reason = "duration_exceeds_every_opening_window"
        message = "No opening window can contain the full visit duration."
    return (
        normalized,
        {},
        frozenset(unknown_days),
        _exclusion(normalized, reason, message),
    )


def _prepare_food(
    candidate: PlannerFoodCandidate,
    trip: PlannerTrip,
) -> tuple[
    PlannerFoodCandidate,
    dict[int, tuple[PlanningWindow, ...]],
    dict[tuple[int, MealType], tuple[PlanningWindow, ...]],
    frozenset[int],
    CandidateExclusion | None,
]:
    normalized = normalize_candidate(candidate)
    if failure := eligibility_failure(normalized, trip):
        return normalized, {}, {}, frozenset(), _exclusion(normalized, *failure)
    if normalized.price.currency != trip.budget.currency:
        return (
            normalized,
            {},
            {},
            frozenset(),
            _exclusion(
                normalized,
                "currency_mismatch",
                "Food price currency does not match the trip budget currency.",
            ),
        )

    day_windows: dict[int, tuple[PlanningWindow, ...]] = {}
    eligibility: dict[tuple[int, MealType], tuple[PlanningWindow, ...]] = {}
    unknown_days: set[int] = set()
    for day in range(1, trip.days + 1):
        opening, unknown = _opening_windows(
            normalized,
            day,
            STANDARD_DAY_END_MINUTE,
        )
        unknown_days.update({day} if unknown else set())
        if opening:
            day_windows[day] = opening
        for meal in normalized.supported_meals:
            policy = MEAL_POLICIES[meal]
            starts = tuple(
                start_window
                for window in opening
                if (
                    start_window := feasible_start_window(
                        window,
                        policy.earliest_start,
                        policy.latest_start,
                        policy.duration_minutes,
                    )
                )
                is not None
            )
            if starts:
                eligibility[(day, meal)] = starts

    if eligibility:
        return normalized, day_windows, eligibility, frozenset(unknown_days), None
    return (
        normalized,
        {},
        {},
        frozenset(unknown_days),
        _exclusion(
            normalized,
            "unsupported_meal_coverage",
            "Food is not open for any supported meal window during the trip.",
        ),
    )


def prepare_planning_problem(payload: ItineraryPlannerInput) -> PreparedPlanningProblem:
    trip = normalize_trip(payload.trip)
    valid_places: list[PlannerCandidate] = []
    valid_food: list[PlannerFoodCandidate] = []
    valid_entertainment: list[PlannerEntertainmentCandidate] = []
    feasible_days: dict[str, frozenset[int]] = {}
    feasible_windows: dict[CandidateDay, tuple[PlanningWindow, ...]] = {}
    meal_eligibility: dict[MealSlot, tuple[PlanningWindow, ...]] = {}
    unknown_days_by_id: dict[str, frozenset[int]] = {}
    unscheduled = [
        CandidateExclusion(
            place_id=item.place_id,
            name=item.name,
            priority=item.priority,
            reason_code=item.reason_code,
            message=item.message,
            source_refs=tuple(item.source_refs),
        )
        for item in payload.excluded_candidates
    ]
    discarded: list[CandidateExclusion] = []
    warnings = list(payload.upstream_warnings)
    accommodation_nights = max(0, trip.days - 1)
    accommodations = tuple(payload.accommodations) if accommodation_nights else ()
    accommodation_by_id = {item.place_id: item for item in accommodations}
    inferred_rooms = max(1, ceil(trip.people / 2))
    accommodation_cost_by_id = {
        item.place_id: ceil(item.price_per_night.cost * inferred_rooms / trip.people)
        for item in accommodations
    }

    for candidate in payload.places:
        normalized, windows, unknown_days, exclusion = _prepare_place(candidate, trip)
        if exclusion:
            _store_exclusion(exclusion, unscheduled, discarded)
            continue
        valid_places.append(normalized)
        feasible_days[normalized.place_id] = frozenset(windows)
        feasible_windows.update(
            {(normalized.place_id, day): value for day, value in windows.items()}
        )
        if unknown_days:
            unknown_days_by_id[normalized.place_id] = unknown_days

    for candidate in payload.food:
        normalized, windows, eligibility, unknown_days, exclusion = _prepare_food(
            candidate, trip
        )
        if exclusion:
            _store_exclusion(exclusion, unscheduled, discarded)
            continue
        valid_food.append(normalized)
        feasible_days[normalized.place_id] = frozenset(windows)
        feasible_windows.update(
            {(normalized.place_id, day): value for day, value in windows.items()}
        )
        meal_eligibility.update(
            {
                (normalized.place_id, day, meal): value
                for (day, meal), value in eligibility.items()
            }
        )
        if unknown_days:
            unknown_days_by_id[normalized.place_id] = unknown_days

    for candidate in payload.entertainment or []:
        normalized, windows, unknown_days, exclusion = _prepare_place(candidate, trip)
        if exclusion:
            _store_exclusion(exclusion, unscheduled, discarded)
            continue
        valid_entertainment.append(normalized)
        feasible_days[normalized.place_id] = frozenset(windows)
        feasible_windows.update(
            {(normalized.place_id, day): value for day, value in windows.items()}
        )
        if unknown_days:
            unknown_days_by_id[normalized.place_id] = unknown_days

    candidates: list[Candidate] = [*valid_places, *valid_food, *valid_entertainment]
    late_night_eligible_ids = frozenset(
        candidate.place_id
        for candidate in valid_places
        if is_late_night_eligible(candidate)
    )
    candidate_by_id = {candidate.place_id: candidate for candidate in candidates}
    related_by_place: dict[str, frozenset[str]] = {}
    for candidate in candidates:
        valid_targets = {
            target
            for target in candidate.relationships
            if target in candidate_by_id and target != candidate.place_id
        }
        invalid_targets = set(candidate.relationships) - valid_targets
        if invalid_targets:
            warnings.append(
                f"Ignored dangling relationships from {candidate.place_id}: "
                + ", ".join(sorted(invalid_targets))
            )
        related_by_place[candidate.place_id] = frozenset(valid_targets)

    day_domains = project_optional_day_domains(
        days=trip.days,
        places=[*valid_places, *valid_entertainment],
        food=valid_food,
        feasible_days=feasible_days,
        feasible_windows=feasible_windows,
        meal_eligibility=meal_eligibility,
    )
    feasible_days = day_domains.feasible_days
    preferred_days = day_domains.preferred_days
    feasible_windows = day_domains.feasible_windows
    meal_eligibility = day_domains.meal_eligibility
    warnings.extend(day_domains.warnings)
    meal_aliases = dict(day_domains.meal_aliases)
    for alias in day_domains.fallback_food:
        canonical_id = meal_aliases[alias.place_id]
        valid_food.append(alias)
        candidates.append(alias)
        candidate_by_id[alias.place_id] = alias
        related_by_place[alias.place_id] = related_by_place[canonical_id]
        if (
            day := next(iter(feasible_days[alias.place_id]), None)
        ) and day in unknown_days_by_id.get(canonical_id, frozenset()):
            unknown_days_by_id[alias.place_id] = frozenset({day})

    for place_id in unknown_days_by_id:
        warnings.append(
            f"openingHours is unknown for {place_id}; treated as open for the "
            "full itinerary window on affected days."
        )

    missing_meals = tuple(
        MissingMealCoverage(day, meal)
        for day in range(1, trip.days + 1)
        for meal in MealType
        if not any(
            (food.place_id, day, meal) in meal_eligibility for food in valid_food
        )
    )
    if missing_meals:
        raise PlanningPreflightError(missing_meals)

    preferred_windows = {}
    for candidate in candidates:
        latest_end = (
            OVERNIGHT_END_MINUTE
            if candidate.place_id in late_night_eligible_ids
            else STANDARD_DAY_END_MINUTE
        )
        preferred_windows[candidate.place_id] = normalize_and_merge(
            candidate.preferred_time_windows,
            latest_end,
        )
    prepared = PreparedPlanningProblem(
        trip=trip,
        accommodations=accommodations,
        accommodation_by_id=MappingProxyType(accommodation_by_id),
        valid_places=tuple(valid_places),
        valid_food=tuple(valid_food),
        valid_entertainment=tuple(valid_entertainment),
        candidate_by_id=MappingProxyType(candidate_by_id),
        feasible_days=MappingProxyType(feasible_days),
        preferred_days=MappingProxyType(preferred_days),
        feasible_windows=MappingProxyType(feasible_windows),
        preferred_windows=MappingProxyType(preferred_windows),
        meal_eligibility=MappingProxyType(meal_eligibility),
        related_by_place=MappingProxyType(related_by_place),
        unknown_opening_ids=frozenset(unknown_days_by_id),
        unknown_opening_days=MappingProxyType(unknown_days_by_id),
        late_night_eligible_ids=late_night_eligible_ids,
        unscheduled_priority=tuple(unscheduled),
        discarded_optional=tuple(discarded),
        warnings=tuple(warnings),
        accommodation_nights=accommodation_nights,
        accommodation_cost_per_person_by_id=MappingProxyType(accommodation_cost_by_id),
        canonical_place_id_by_candidate_id=MappingProxyType(meal_aliases),
    )
    if trip.days > MAX_OPTIONAL_DAYS and len(valid_places) >= trip.days:
        validate_projected_pool(prepared)
    return prepared
