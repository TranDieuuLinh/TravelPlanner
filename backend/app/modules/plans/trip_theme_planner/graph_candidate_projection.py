"""Pure projection from graph research into TripTheme candidate records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field, model_validator

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
from app.modules.plans.domain.entities import ExperienceCategory


class GraphExperienceCandidate(BaseModel):
    """Bounded identifiers and evidence for one selectable graph experience."""

    claim_ids: list[str] = Field(default_factory=list, alias="claimIds")
    place_ids: list[str] = Field(default_factory=list, alias="placeIds")
    candidate_place_ids: list[str] = Field(
        default_factory=list,
        alias="candidatePlaceIds",
    )
    activity_id: str | None = Field(default=None, alias="activityId")
    activity_name: str | None = Field(default=None, alias="activityName")
    category: ExperienceCategory = ExperienceCategory.main_experience
    anchor_place_ids: list[str] = Field(
        default_factory=list,
        alias="anchorPlaceIds",
    )
    anchor_place_names: dict[str, str] = Field(
        default_factory=dict,
        alias="anchorPlaceNames",
    )
    is_special_experience: bool = Field(
        default=False,
        alias="isSpecialExperience",
    )
    rank_reasons: list[str] = Field(default_factory=list, alias="rankReasons")
    rank: int = Field(ge=1)
    fit: FitResult
    trust: TrustLevel
    recommendation: Recommendation | None = None
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CandidateContract(BaseModel):
    """Small selector-facing contract used after graph projection."""

    activity_id: str | None = Field(default=None, alias="activityId")
    claim_ids: list[str] = Field(default_factory=list, alias="claimIds")
    anchor_place_ids: list[str] = Field(default_factory=list, alias="anchorPlaceIds")
    candidate_place_ids: list[str] = Field(
        default_factory=list, alias="candidatePlaceIds"
    )
    category: ExperienceCategory = ExperienceCategory.main_experience
    recommendation: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list, alias="sourceRefs")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @staticmethod
    def _check_ids(values: list[str], field_name: str) -> list[str]:
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f"{field_name} must contain non-empty IDs.")
        if len(values) != len(set(values)):
            raise ValueError(f"{field_name} must not contain duplicate IDs.")
        return values

    @model_validator(mode="after")
    def validate_ids(self) -> "CandidateContract":
        self._check_ids(self.claim_ids, "claimIds")
        self._check_ids(self.anchor_place_ids, "anchorPlaceIds")
        self._check_ids(self.candidate_place_ids, "candidatePlaceIds")
        return self


class GraphCandidateCatalog(BaseModel):
    """Planner-facing catalog containing selectable graph experiences only."""

    candidates: list[GraphExperienceCandidate] = Field(default_factory=list)

    model_config = {"populate_by_name": True, "extra": "forbid"}


_PLACE_TYPES = frozenset({
    # Schema v7 concrete Place descendants.
    "TravelPlace",
    "Restaurant",
    "DrinkDessert",
    "Accommodation",
    # Read compatibility for graph rows created before the v7 migration.
    "Place",
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
        candidatePlaceIds=_ordered_ids(
            (ranked.rank, place_id)
            for ranked in ordered
            for place_id in _place_ids(ranked.claim)
        ),
        activityId=_activity_id(primary.claim),
        activityName=_activity_name(primary.claim),
        anchorPlaceIds=_ordered_ids(
            (ranked.rank, anchor_id)
            for ranked in ordered
            if (anchor_id := _anchor_place_id(ranked.claim)) is not None
        ),
        anchorPlaceNames=_anchor_place_names(ordered),
        isSpecialExperience=any(
            ranked.claim.predicate == "SPECIAL_EXPERIENCE"
            for ranked in ordered
        ),
        rankReasons=list(dict.fromkeys(
            reason
            for ranked in ordered
            for reason in ranked.rankReasons
        )),
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


def _activity_name(claim: GraphEvidenceClaim) -> str | None:
    if claim.activity is not None:
        return claim.activity.name
    if claim.object.type in _ACTIVITY_TYPES:
        return claim.object.name
    return None


def _anchor_place_names(
    experiences: Sequence[RankedExperience],
) -> dict[str, str]:
    names: dict[str, str] = {}
    for ranked in sorted(experiences, key=_ranked_sort_key):
        anchor = ranked.claim.anchorPlace
        if anchor is not None:
            names.setdefault(anchor.id, anchor.name)
        elif (
            ranked.claim.predicate == "OFFERS_ACTIVITY"
            and ranked.claim.subject.type in _PLACE_TYPES
        ):
            names.setdefault(ranked.claim.subject.id, ranked.claim.subject.name)
    return dict(sorted(names.items()))


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


def build_candidate_contract(fixture: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a selector candidate fixture and return its public payload.

    This small adapter is intentionally independent from LLM output. It is useful
    for contract tests and for callers that already have graph-normalized data.
    Timing follows the contract order: edge recommendation, node property, then
    the neutral selector default.
    """

    data = dict(fixture)
    claim_ids = data.get("claimIds", data.get("evidenceClaimIds", []))
    candidate_place_ids = data.get(
        "candidatePlaceIds", data.get("placeIds", [])
    )
    recommendation = dict(data.get("recommendation") or {})
    edge_slots = recommendation.get("timeSlots")
    node = data.get("nodeProperties") or data.get("node") or {}
    node_slots = node.get("timeSlots", node.get("best_time_slots")) if isinstance(node, Mapping) else None
    slots = edge_slots or node_slots or []
    result = {
        "activityId": data.get("activityId"),
        "claimIds": list(claim_ids or []),
        "anchorPlaceIds": list(data.get("anchorPlaceIds", [])),
        "candidatePlaceIds": list(candidate_place_ids or []),
        "category": data.get("category", ExperienceCategory.main_experience),
        "recommendation": {**recommendation, "timeSlots": list(slots)},
        "sourceRefs": list(data.get("sourceRefs", [])),
    }
    return CandidateContract.model_validate(result).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


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
    "CandidateContract",
    "build_graph_candidate_catalog",
    "build_candidate_contract",
    "project_graph_candidate_catalog",
]
