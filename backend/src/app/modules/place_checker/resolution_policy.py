from app.modules.place_checker.contract import PlaceCandidateInput
from app.modules.place_checker.enums import SourceTier
from app.modules.place_checker.resolution_contract import PlaceMatchOption
from app.shared.tools.search_places import PlaceSearchResult


def select_provisional_option(
    candidate: PlaceCandidateInput,
    result: PlaceSearchResult,
    options: list[PlaceMatchOption],
) -> PlaceMatchOption | None:
    """Select one best direct/URL match for the Planner handoff.

    Place Checker no longer exposes an ambiguity branch to the frontend. The
    search provider still receives the address hint, and this final selection
    prefers its address-compatible result when an address hint exists. A
    selected result remains provisional so the warning and provenance survive
    the Planner handoff.
    """
    if candidate.source_tier not in {SourceTier.direct_user, SourceTier.url}:
        return None
    if result.resolution_reason in {
        "knowledge_graph_provider_error",
        "external_provider_error",
        "search_places_unexpected_error",
    }:
        return None
    eligible = [
        option
        for option in options
        if option.eligible_destination and not option.identity_conflicts
    ]
    if not eligible:
        return None
    address_hint = candidate.address_hint or next(
        (
            source.address_hint
            for source in candidate.source_places
            if source.address_hint
        ),
        None,
    )
    if address_hint:
        return max(
            eligible,
            key=lambda option: (
                option.components.address_score
                if option.components.address_score is not None
                else -1.0,
                option.score,
                -option.rank,
            ),
        )
    return max(eligible, key=lambda option: (option.score, -option.rank))
