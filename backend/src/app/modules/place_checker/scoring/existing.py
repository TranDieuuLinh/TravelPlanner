from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.planning.category import planner_category_for_candidate
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.normalization import normalize_text


def existing_pool_signals(
    places: PlaceEvaluationBatch,
) -> tuple[set[str], set[str], list[Coordinates]]:
    categories: set[str] = set()
    experiences: set[str] = set()
    anchors: list[Coordinates] = []
    for evaluation in places.places:
        if not evaluation.planner_eligible or evaluation.place.metadata is None:
            continue
        metadata = evaluation.place.metadata
        if metadata.category:
            categories.add(
                planner_category_for_candidate(
                    metadata.category,
                    name=evaluation.place.canonical_name,
                    tags=metadata.tags,
                )
            )
        experiences.update(normalize_text(tag) for tag in metadata.tags if tag)
        if metadata.coordinates:
            anchors.append(metadata.coordinates)
    return categories, experiences, anchors
