"""Pure projection from graph research into TripTheme candidate records."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from app.modules.knowledge_graph.research import (
    CheckStatus,
    FitResult,
    GraphEvidenceClaim,
    RankedExperience,
    Recommendation,
    RecommendationPriority,
    TripResearchBundle,
    TrustLevel,
)


class GraphExperienceCandidate(BaseModel):
    """Bounded identifiers and evidence for one selectable graph experience."""

    claim_ids: list[str] = Field(default_factory=list, alias="claimIds")
    place_ids: list[str] = Field(default_factory=list, alias="placeIds")
    activity_id: str | None = Field(default=None, alias="activityId")
    anchor_place_ids: list[str] = Field(
        default_factory=list,
        alias="anchorPlaceIds",
    )
    rank: int = Field(ge=1)
    fit: FitResult
    trust: TrustLevel
    recommendation: Recommendation | None = None
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class GraphCandidateCatalog(BaseModel):
    """Planner-facing catalog containing selectable graph experiences only."""

    candidates: list[GraphExperienceCandidate] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "forbid"}


_PLACE_TYPES = frozenset({
    "Place",
    "Restaurant",
    "TravelPlace",
    "Cafe",
    "Hotel",
    "Shop",
    "Attraction",
    "Entertainment",
})
_ACTIVITY_TYPES = frozenset({"Activity", "Event", "Tour", "Workshop", "Class"})
_PRIORITY_ORDER = {
    RecommendationPriority.MUST: 0,
    RecommendationPriority.RECOMMENDED: 1,
    RecommendationPriority.OPTIONAL: 2,
}


def project_graph_candidate_catalog(
    bundle: TripResearchBundle,
) -> GraphCandidateCatalog:
    """Project supported eligible experiences without reading other bundle lists."""

    grouped: dict[str, list[RankedExperience]] = {}
    for ranked in bundle.eligibleExperiences:
        if not _is_selectable(ranked):
            continue
        grouped.setdefault(_candidate_key(ranked.claim), []).append(ranked)

    candidates = [
        _project_group(experiences)
        for experiences in grouped.values()
    ]
    candidates.sort(key=_candidate_sort_key)
    return GraphCandidateCatalog(candidates=candidates)


def _is_selectable(ranked: RankedExperience) -> bool:
    if (
        ranked.fit.status is not CheckStatus.SUPPORTED
        or ranked.fit.hasHardConflict
    ):
        return False
    return _claim_shape(ranked.claim) is not None


def _claim_shape(claim: GraphEvidenceClaim) -> str | None:
    activity_id = _activity_id(claim)
    anchor_id = _anchor_place_id(claim)
    has_offers_activity = (
        claim.predicate == "OFFERS_ACTIVITY"
        or "OFFERS_ACTIVITY" in claim.path
    )
    if activity_id and anchor_id and has_offers_activity:
        return "place_offers_activity"
    if claim.predicate != "SPECIAL_EXPERIENCE":
        return None
    if claim.object.type in _ACTIVITY_TYPES:
        return "special_experience_activity"
    if claim.object.type in _PLACE_TYPES:
        return "special_experience_place"
    return None


def _candidate_key(claim: GraphEvidenceClaim) -> str:
    activity_id = _activity_id(claim)
    if activity_id is not None:
        return f"activity:{activity_id}"
    return f"place:{claim.object.id}"


def _activity_id(claim: GraphEvidenceClaim) -> str | None:
    if claim.activity is not None:
        return claim.activity.id
    if claim.object.type in _ACTIVITY_TYPES and claim.predicate in {
        "SPECIAL_EXPERIENCE",
        "OFFERS_ACTIVITY",
    }:
        return claim.object.id
    return None


def _anchor_place_id(claim: GraphEvidenceClaim) -> str | None:
    if claim.anchorPlace is not None:
        return claim.anchorPlace.id
    if claim.predicate == "OFFERS_ACTIVITY" and claim.subject.type in _PLACE_TYPES:
        return claim.subject.id
    return None


def _project_group(
    experiences: Sequence[RankedExperience],
) -> GraphExperienceCandidate:
    ordered = sorted(experiences, key=_ranked_sort_key)
    primary = ordered[0]
    claims = [ranked.claim for ranked in ordered]

    return GraphExperienceCandidate(
        claimIds=_ordered_ids(
            (ranked.rank, ranked.claim.claimId) for ranked in ordered
        ),
        placeIds=_ordered_ids(
            (ranked.rank, place_id)
            for ranked in ordered
            for place_id in _place_ids(ranked.claim)
        ),
        activityId=_activity_id(primary.claim),
        anchorPlaceIds=_ordered_ids(
            (ranked.rank, anchor_id)
            for ranked in ordered
            if (anchor_id := _anchor_place_id(ranked.claim)) is not None
        ),
        rank=primary.rank,
        fit=primary.fit,
        trust=primary.claim.trust,
        recommendation=_best_recommendation(ordered),
        sourceRefs=sorted({
            evidence.source
            for claim in claims
            for evidence in claim.evidence
            if evidence.source
        }),
    )


def _place_ids(claim: GraphEvidenceClaim) -> set[str]:
    place_ids: set[str] = set()
    if claim.object.type in _PLACE_TYPES:
        place_ids.add(claim.object.id)
    if claim.predicate == "OFFERS_ACTIVITY" and claim.subject.type in _PLACE_TYPES:
        place_ids.add(claim.subject.id)
    if claim.anchorPlace is not None:
        place_ids.add(claim.anchorPlace.id)
    return place_ids


def _ordered_ids(entries: Iterable[tuple[int, str]]) -> list[str]:
    best_rank_by_id: dict[str, int] = {}
    for rank, entity_id in entries:
        best_rank_by_id[entity_id] = min(
            rank,
            best_rank_by_id.get(entity_id, rank),
        )
    return [
        entity_id
        for entity_id, _ in sorted(
            best_rank_by_id.items(),
            key=lambda item: (item[1], item[0]),
        )
    ]


def _best_recommendation(
    experiences: Sequence[RankedExperience],
) -> Recommendation | None:
    ranked_recommendations = [
        (
            _PRIORITY_ORDER[recommendation.priority],
            ranked.rank,
            ranked.claim.claimId,
            recommendation.model_dump_json(),
            recommendation,
        )
        for ranked in experiences
        for recommendation in ranked.claim.recommendations
    ]
    if not ranked_recommendations:
        return None
    return min(ranked_recommendations, key=lambda entry: entry[:4])[4]


def _ranked_sort_key(ranked: RankedExperience) -> tuple[int, str, str]:
    return (
        ranked.rank,
        ranked.claim.claimId,
        ranked.model_dump_json(),
    )


def _candidate_sort_key(
    candidate: GraphExperienceCandidate,
) -> tuple[int, str, tuple[str, ...], tuple[str, ...]]:
    return (
        candidate.rank,
        candidate.activity_id or "",
        tuple(candidate.place_ids),
        tuple(candidate.claim_ids),
    )


build_graph_candidate_catalog = project_graph_candidate_catalog


__all__ = [
    "GraphCandidateCatalog",
    "GraphExperienceCandidate",
    "build_graph_candidate_catalog",
    "project_graph_candidate_catalog",
]
