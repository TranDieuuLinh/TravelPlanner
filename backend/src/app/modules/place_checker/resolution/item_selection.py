from app.modules.place_checker.contract import InputItem
from app.modules.place_checker.resolution.item_contract import ItemPlaceOption
from app.shared.tools.search_places import PlaceSearchResult


def selected_confidence(
    item: InputItem,
    selected: ItemPlaceOption | None,
    result: PlaceSearchResult,
) -> float | None:
    if selected is None:
        return None
    selected_match = next(
        (match for match in result.top_matches if match.place_id == selected.place_id),
        None,
    )
    identity_score = max(
        selected.score,
        (
            selected_match.score_components.get("nameSimilarity", 0)
            if selected_match is not None
            else 0
        ),
    )
    return round(item.confidence * identity_score, 6)


def selection_reason(
    selected: ItemPlaceOption | None,
    result: PlaceSearchResult,
) -> str:
    original_top_id = next(
        (
            match.place_id
            for match in result.top_matches
            if not match.rejection_reasons
        ),
        None,
    )
    if (
        selected is not None
        and original_top_id is not None
        and selected.place_id != original_top_id
    ):
        return "context_and_proximity_reranked_requirement_match"
    if selected is not None or result.status == "provider_error":
        return result.resolution_reason
    return "no_eligible_item_venue"
