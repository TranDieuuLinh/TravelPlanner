from collections import Counter

from app.modules.place_checker.evaluation.contract import PlaceEvaluationBatch
from app.modules.place_checker.planning.category import planner_category_for_candidate
from app.modules.place_checker.scoring.tag_policy import CandidateTagPolicy
from app.shared.contracts.place import Coordinates


def existing_pool_signals(
    places: PlaceEvaluationBatch,
    allowed_tags: frozenset[str],
) -> tuple[Counter[str], list[Coordinates]]:
    tag_counts: Counter[str] = Counter()
    anchors: list[Coordinates] = []
    for evaluation in places.places:
        if not evaluation.planner_eligible or evaluation.place.metadata is None:
            continue
        metadata = evaluation.place.metadata
        category = planner_category_for_candidate(
            metadata.category,
            name=evaluation.place.canonical_name,
            tags=metadata.tags,
        )
        if category == "travel_place":
            tag_counts.update(
                CandidateTagPolicy.existing_tags(metadata.tags, allowed_tags)
            )
        if metadata.coordinates:
            anchors.append(metadata.coordinates)
    return tag_counts, anchors
