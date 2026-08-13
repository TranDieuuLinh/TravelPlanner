from app.modules.place_checker.contract import PlaceCandidateInput
from app.modules.place_checker.enums import SimilarityMethod, SourceTier
from app.modules.place_checker.resolution_contract import PlaceMatchOption
from app.shared.tools.search_places import PlaceSearchResult


PROVISIONAL_MIN_SCORE = 0.68
PROVISIONAL_MIN_NAME_SCORE = 0.72


def select_provisional_option(
    candidate: PlaceCandidateInput,
    result: PlaceSearchResult,
    options: list[PlaceMatchOption],
) -> PlaceMatchOption | None:
    """Keep trusted-input ambiguity without accepting weak lexical collisions."""
    if candidate.source_tier not in {SourceTier.direct_user, SourceTier.url}:
        return None
    if result.status not in {"needs_review", "unresolved"}:
        return None
    if result.resolution_reason in {
        "knowledge_graph_provider_error",
        "external_provider_error",
    }:
        return None
    eligible = [
        option
        for option in options
        if option.eligible_destination and not option.identity_conflicts
    ]
    if not eligible:
        return None
    best = eligible[0]
    name_score = max(
        best.components.lexical_score,
        best.components.alias_score or 0,
        best.components.semantic_score or 0,
    )
    if best.score < PROVISIONAL_MIN_SCORE or name_score < PROVISIONAL_MIN_NAME_SCORE:
        return None
    has_strong_identity_signal = (
        best.method in {SimilarityMethod.exact, SimilarityMethod.alias}
        or (best.components.address_score or 0) >= 0.45
        or (best.components.semantic_score or 0) >= 0.88
    )
    return best if has_strong_identity_signal else None
