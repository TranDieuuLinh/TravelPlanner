from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Mapping

from app.modules.itinerary_planner.contract import (
    CandidatePriority,
    CandidateSourceKind,
    FoodVenueType,
    MealType,
    PlannerCandidate,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.hybrid.popular_place_reservation import (
    available_candidate_ids,
)
from app.modules.itinerary_planner.optimizer.popular_place_coverage import (
    popular_place_ids,
)
from app.modules.itinerary_planner.optimizer.tag_diversity import meaningful_tags
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.quality import (
    bayesian_quality_by_id,
    popularity_by_id,
)
from app.modules.itinerary_planner.routing_models import RoutingProblem

MAX_ACTIVITY_CANDIDATES = 16
FOOD_OPTIONS_PER_MEAL = 3
DEFAULT_QUALITY_MAX = 300
SPECIAL_EXPERIENCE_SCORE = 8_000
PREFERENCE_MATCH_SCORE = 2_000
POPULARITY_SCORE_MAX = 1_500
POPULAR_PLACE_SCORE = 6_000
RELATIONSHIP_SCORE = 250
TRIP_TAG_REPEAT_SCORE = 10_000
PRIORITY_VALUES = {CandidatePriority.user_input, CandidatePriority.url}


@dataclass(frozen=True, slots=True)
class DayShortlist:
    candidate_ids: frozenset[str]
    hinted_order: tuple[str, ...]


def build_day_shortlist(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    day: int,
    used_ids: frozenset[str],
    quality_max: int = DEFAULT_QUALITY_MAX,
    trip_tag_counts: Mapping[str, int] | None = None,
) -> DayShortlist:
    quality_by_id = bayesian_quality_by_id(problem.candidate_by_id.values())
    popularity = popularity_by_id(problem.candidate_by_id.values())
    popular_places = popular_place_ids(problem)
    special_places = frozenset(
        candidate.place_id
        for candidate in problem.valid_places
        if candidate.source_kind
        in {CandidateSourceKind.special_experience, CandidateSourceKind.both}
    )
    food_ids = {item.place_id for item in problem.valid_food}
    available = available_candidate_ids(
        problem,
        day=day,
        used_ids=used_ids,
        popular_ids=popular_places,
        special_ids=special_places,
    )
    activities = [
        problem.candidate_by_id[candidate_id]
        for candidate_id in sorted(available - food_ids)
    ]
    foods = [
        problem.candidate_by_id[candidate_id]
        for candidate_id in sorted(available & food_ids)
    ]
    selected_activities = _select_activities(
        problem,
        activities,
        routing,
        quality_by_id,
        popularity,
        popular_places,
        quality_max,
        trip_tag_counts or {},
    )
    improved_activities = _improve_activity_order(
        tuple(item.place_id for item in selected_activities), routing
    )
    food_options: dict[MealType, tuple[str, ...]] = {}
    selected_food: dict[MealType, str] = {}
    corridors = _meal_corridors(improved_activities)
    for meal in MealType:
        eligible = [
            item
            for item in foods
            if (item.place_id, day, meal) in problem.meal_eligibility
        ]
        ranked = sorted(
            eligible,
            key=lambda item: (
                _corridor_travel_minutes(
                    item.place_id,
                    corridors[meal],
                    routing,
                ),
                -_candidate_score(
                    problem,
                    item,
                    quality_by_id,
                    popularity,
                    popular_places,
                    quality_max,
                ),
                item.place_id,
            ),
        )
        options = _food_options(ranked)
        food_options[meal] = options
        if options:
            selected_food[meal] = options[0]

    order = _interleave_meals(improved_activities, selected_food)
    candidate_ids = frozenset(
        [
            *improved_activities,
            *(item for values in food_options.values() for item in values),
        ]
    )
    return DayShortlist(
        candidate_ids=candidate_ids,
        hinted_order=order,
    )


def _food_options(ranked: list[PlannerFoodCandidate]) -> tuple[str, ...]:
    selected = list(ranked[:FOOD_OPTIONS_PER_MEAL])
    if selected and all(
        item.venue_type == FoodVenueType.drink_dessert
        for item in selected
    ):
        restaurant = next(
            (
                item
                for item in ranked[FOOD_OPTIONS_PER_MEAL:]
                if item.venue_type == FoodVenueType.restaurant
            ),
            None,
        )
        if restaurant is not None:
            selected[-1] = restaurant
    return tuple(item.place_id for item in selected)


def full_day_candidate_ids(
    problem: PreparedPlanningProblem,
    *,
    day: int,
    used_ids: frozenset[str],
) -> frozenset[str]:
    return frozenset(
        candidate_id
        for candidate_id, feasible in problem.feasible_days.items()
        if day in feasible and candidate_id not in used_ids
    )


def _select_activities(
    problem: PreparedPlanningProblem,
    candidates: list[PlannerCandidate],
    routing: RoutingProblem,
    quality_by_id: dict[str, float],
    popularity: dict[str, float],
    popular_places: frozenset[str],
    quality_max: int,
    trip_tag_counts: Mapping[str, int],
) -> tuple[PlannerCandidate, ...]:
    priority = [item for item in candidates if item.priority in PRIORITY_VALUES]
    optional = [item for item in candidates if item.priority not in PRIORITY_VALUES]
    optional_slots = max(0, MAX_ACTIVITY_CANDIDATES - len(priority))
    selected = list(priority)
    while optional and len(selected) < len(priority) + optional_slots:
        chosen = max(
            optional,
            key=lambda item: (
                _candidate_score(
                    problem,
                    item,
                    quality_by_id,
                    popularity,
                    popular_places,
                    quality_max,
                )
                - 25 * _cluster_travel_minutes(item.place_id, selected, routing)
                - _trip_tag_repeat_penalty(item, trip_tag_counts),
                item.place_id,
            ),
        )
        selected.append(chosen)
        optional.remove(chosen)
    return tuple(selected)


def _trip_tag_repeat_penalty(
    candidate: PlannerCandidate,
    trip_tag_counts: Mapping[str, int],
) -> int:
    if not trip_tag_counts:
        return 0
    groups = meaningful_tags(candidate.tags)
    if not groups:
        return TRIP_TAG_REPEAT_SCORE
    if any(not trip_tag_counts.get(tag, 0) for tag in groups):
        return 0
    return TRIP_TAG_REPEAT_SCORE * sum(
        trip_tag_counts.get(tag, 0) for tag in groups
    )


def _cluster_travel_minutes(
    candidate_id: str,
    selected: list[PlannerCandidate],
    routing: RoutingProblem,
) -> int:
    if not selected:
        return 0
    missing = 10**6
    return min(
        min(
            routing.travel_by_candidate_pair.get(
                (candidate_id, item.place_id)
            ).safe_minutes
            if (candidate_id, item.place_id) in routing.travel_by_candidate_pair
            else missing,
            routing.travel_by_candidate_pair.get(
                (item.place_id, candidate_id)
            ).safe_minutes
            if (item.place_id, candidate_id) in routing.travel_by_candidate_pair
            else missing,
        )
        for item in selected
    )


def _candidate_score(
    problem: PreparedPlanningProblem,
    candidate: PlannerCandidate,
    quality_by_id: dict[str, float],
    popularity: dict[str, float],
    popular_places: frozenset[str],
    quality_max: int,
) -> int:
    priority = {
        CandidatePriority.user_input: 1_000_000,
        CandidatePriority.url: 100_000,
        CandidatePriority.special_experience: 0,
        CandidatePriority.special_near: 0,
    }[candidate.priority]
    normalized_tags = set(candidate.tags)
    preference = (
        len(normalized_tags & set(problem.trip.preferences.tags))
        * PREFERENCE_MATCH_SCORE
    )
    style = (
        len(set(candidate.styles) & set(problem.trip.preferences.styles))
        * PREFERENCE_MATCH_SCORE
    )
    special = (
        SPECIAL_EXPERIENCE_SCORE
        if candidate.source_kind
        in {CandidateSourceKind.special_experience, CandidateSourceKind.both}
        else 0
    )
    quality = round(quality_by_id[candidate.place_id] * quality_max)
    popular = round(popularity[candidate.place_id] * POPULARITY_SCORE_MAX)
    popular_place = (
        POPULAR_PLACE_SCORE if candidate.place_id in popular_places else 0
    )
    relationship = len(candidate.relationships) * RELATIONSHIP_SCORE
    return (
        priority
        + special
        + preference
        + style
        + popular
        + popular_place
        + quality
        + relationship
    )


def _improve_activity_order(
    ordered: tuple[str, ...], routing: RoutingProblem
) -> tuple[str, ...]:
    if len(ordered) < 3:
        return ordered
    best = ordered
    best_cost = _route_cost(best, routing)
    improved = True
    while improved:
        improved = False
        for left in range(len(best) - 1):
            for right in range(left + 1, len(best)):
                candidate = (
                    *best[:left],
                    *reversed(best[left : right + 1]),
                    *best[right + 1 :],
                )
                cost = _route_cost(candidate, routing)
                if cost < best_cost:
                    best, best_cost, improved = candidate, cost, True
        for left in range(len(best) - 1):
            for right in range(left + 1, len(best)):
                candidate = list(best)
                candidate[left], candidate[right] = candidate[right], candidate[left]
                candidate_tuple = tuple(candidate)
                cost = _route_cost(candidate_tuple, routing)
                if cost < best_cost:
                    best, best_cost, improved = candidate_tuple, cost, True
    return best


def _route_cost(ordered: tuple[str, ...], routing: RoutingProblem) -> int:
    missing = 10**6
    return sum(
        routing.travel_by_candidate_pair.get((origin, destination), None).safe_minutes
        if (origin, destination) in routing.travel_by_candidate_pair
        else missing
        for origin, destination in pairwise(ordered)
    )


def _interleave_meals(
    activities: tuple[str, ...], selected_food: dict[MealType, str]
) -> tuple[str, ...]:
    first_cut, second_cut = _activity_cuts(activities)
    ordered: list[str] = []
    if breakfast := selected_food.get(MealType.breakfast):
        ordered.append(breakfast)
    ordered.extend(activities[:first_cut])
    if lunch := selected_food.get(MealType.lunch):
        ordered.append(lunch)
    ordered.extend(activities[first_cut:second_cut])
    if dinner := selected_food.get(MealType.dinner):
        ordered.append(dinner)
    ordered.extend(activities[second_cut:])
    return tuple(ordered)


def _meal_corridors(
    activities: tuple[str, ...],
) -> dict[MealType, tuple[str | None, str | None]]:
    first_cut, second_cut = _activity_cuts(activities)
    return {
        MealType.breakfast: (None, activities[0] if activities else None),
        MealType.lunch: (
            activities[first_cut - 1] if first_cut else None,
            activities[first_cut] if first_cut < len(activities) else None,
        ),
        MealType.dinner: (
            activities[second_cut - 1] if second_cut else None,
            activities[second_cut] if second_cut < len(activities) else None,
        ),
    }


def _activity_cuts(activities: tuple[str, ...]) -> tuple[int, int]:
    if not activities:
        return 0, 0
    first_cut = max(1, len(activities) // 3)
    return first_cut, len(activities)


def _corridor_travel_minutes(
    food_id: str,
    corridor: tuple[str | None, str | None],
    routing: RoutingProblem,
) -> int:
    before, after = corridor
    pairs = [
        pair
        for pair in ((before, food_id), (food_id, after))
        if pair[0] is not None and pair[1] is not None
    ]
    missing = 10**6
    return sum(
        routing.travel_by_candidate_pair[pair].safe_minutes
        if pair in routing.travel_by_candidate_pair
        else missing
        for pair in pairs
    )
