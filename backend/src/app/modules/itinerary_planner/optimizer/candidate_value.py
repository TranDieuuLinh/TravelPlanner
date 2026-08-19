from app.modules.itinerary_planner.contract import CandidatePriority, CandidateSourceKind
from app.modules.itinerary_planner.quality import bayesian_adjusted_rating_by_id


def build_special_value(problem, variables, weights):
    return sum(
        variables.selected[candidate_id] * weights.special_experience
        for candidate_id, candidate in problem.candidate_by_id.items()
        if candidate.source_kind
        in {CandidateSourceKind.special_experience, CandidateSourceKind.both}
    )


def build_preference_value(problem, variables, weights):
    preferences = set(problem.trip.preferences.tags)
    if not preferences:
        return 0
    return sum(
        variables.selected[candidate_id]
        * round(
            len(preferences & set(candidate.tags))
            / len(preferences)
            * weights.preference_max
        )
        for candidate_id, candidate in problem.candidate_by_id.items()
    )


def build_style_value(problem, variables, weights):
    styles = set(problem.trip.preferences.styles)
    if not styles:
        return 0
    return sum(
        variables.selected[candidate_id]
        * round(len(styles & set(candidate.styles)) / len(styles) * weights.style_max)
        for candidate_id, candidate in problem.candidate_by_id.items()
    )


def build_low_confidence_generic_place_cost(problem, variables, weight):
    return sum(
        variables.selected[candidate.place_id] * weight
        for candidate in problem.valid_places
        if candidate.source_kind == CandidateSourceKind.generic
        and candidate.priority
        not in {CandidatePriority.user_input, CandidatePriority.url}
        and (candidate.review_count or 0) < 500
    )


def build_low_quality_food_cost(problem, variables, weight):
    bayesian_ratings = bayesian_adjusted_rating_by_id(
        problem.candidate_by_id.values()
    )
    return sum(
        variables.selected[candidate.place_id]
        * (
            weight * int((bayesian_ratings.get(candidate.place_id) or 0) < 4.0)
            + weight // 3 * int((candidate.review_count or 0) < 100)
        )
        for candidate in problem.valid_food
    )
