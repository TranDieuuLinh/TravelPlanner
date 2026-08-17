from app.modules.itinerary_planner.contract import CandidateSourceKind


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
