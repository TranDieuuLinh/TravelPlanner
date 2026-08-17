from __future__ import annotations

from app.modules.itinerary_planner.beam_search.constraints import (
    is_drink_dessert,
    is_entertainment,
    is_restaurant,
    is_travelplace,
)


def candidate_score(problem, candidate, state, start, travel, quality, config):
    preferences = set(problem.trip.preferences.tags)
    styles = set(problem.trip.preferences.styles)
    tag_value = len(set(candidate.tags) & preferences) / max(1, len(preferences))
    style_value = len(set(candidate.styles) & styles) / max(1, len(styles))
    time_value = 1.0
    if candidate.preferred_time_windows:
        time_value = max(
            0.0,
            1.0
            - min(
                abs(start - window.start_minute) / 180.0
                for window in candidate.preferred_time_windows
            ),
        )
    travel_value = 1.0 if travel is None else max(0.0, 1.0 - travel.safe_minutes / 180.0)
    budget_value = 1.0
    if problem.trip.budget.amount:
        budget_value = max(0.0, 1.0 - candidate.price.cost / problem.trip.budget.amount)
    selected_tags = {
        tag
        for stop in state.stops
        for tag in problem.candidate_by_id[stop.place_id].tags
    }
    diversity_value = 1.0 if not selected_tags.intersection(candidate.tags) else 0.25
    relationship_value = float(
        bool(state.last_id and candidate.place_id in problem.related_by_place.get(state.last_id, ()))
    )
    weights = config.weights
    if is_travelplace(candidate):
        quality_multiplier = weights.travelplace_quality_multiplier
    elif is_restaurant(candidate):
        quality_multiplier = weights.restaurant_quality_multiplier
    elif is_drink_dessert(candidate):
        quality_multiplier = weights.drink_dessert_quality_multiplier
    elif is_entertainment(candidate):
        quality_multiplier = weights.entertainment_quality_multiplier
    else:
        quality_multiplier = 1.0
    selected_travelplace_ids = {
        stop.place_id
        for stop in state.stops
        if is_travelplace(problem.candidate_by_id[stop.place_id])
    }
    travelplace_day_bonus = (
        weights.travelplace_day_bonus * (1 + 0.5 * len(selected_travelplace_ids))
        if is_travelplace(candidate) and candidate.place_id not in selected_travelplace_ids
        else 0
    )
    return (
        quality[candidate.place_id] * weights.quality * quality_multiplier
        + tag_value * weights.preference
        + style_value * weights.style
        + time_value * weights.time_fit
        + travel_value * weights.travel
        + budget_value * weights.budget
        + diversity_value * weights.diversity
        + relationship_value * weights.relationship
        + float(is_restaurant(candidate)) * weights.restaurant_coverage
        + travelplace_day_bonus
    )
