"""Pure validation of required experiences against graph evidence."""

from __future__ import annotations

from collections.abc import Iterable

from app.modules.knowledge_graph.research import (
    CheckStatus,
    EdgeEvidence,
    GraphEvidenceClaim,
    TripResearchBundle,
)
from app.modules.plans.dto.agent_contracts import (
    RequiredExperience,
    RequiredExperienceSelectionPolicy,
)
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    GraphCandidateCatalog,
    _activity_id,
    _anchor_place_id,
    _place_ids,
)


class RequiredExperienceGraphValidationError(ValueError):
    """Raised when a requirement references unsupported graph evidence."""


def validate_required_experience(
    requirement: RequiredExperience,
    evidence: TripResearchBundle | GraphCandidateCatalog,
) -> RequiredExperience:
    """Validate one requirement against a bounded research graph/catalog."""
    claims = _claims(evidence)
    claim_by_id = {claim.claimId: claim for claim in claims}
    if len(claim_by_id) != len(claims):
        raise RequiredExperienceGraphValidationError("duplicate claim IDs in evidence")

    selected_claims = []
    for claim_id in requirement.evidence_claim_ids:
        claim = claim_by_id.get(claim_id)
        if claim is None:
            raise RequiredExperienceGraphValidationError(
                f"unknown evidence claim ID: {claim_id}"
            )
        selected_claims.append(claim)

    if len(set(requirement.evidence_claim_ids)) != len(requirement.evidence_claim_ids):
        raise RequiredExperienceGraphValidationError("duplicate evidence claim IDs")
    evidence_sources = {
        source
        for claim in selected_claims
        for item in claim.evidence
        if (source := item.source)
    }
    missing_sources = set(requirement.source_refs) - evidence_sources
    if missing_sources:
        raise RequiredExperienceGraphValidationError(
            f"sourceRefs not present in evidence: {sorted(missing_sources)}"
        )

    place_ids = {place_id for claim in selected_claims for place_id in _place_ids(claim)}
    activities = {_activity_id(claim) for claim in selected_claims} - {None}
    policy = requirement.selection_policy
    if policy is RequiredExperienceSelectionPolicy.required_anchor:
        if not set(requirement.anchor_place_ids) <= place_ids:
            raise RequiredExperienceGraphValidationError("anchor place is not evidence-backed")
    elif policy is RequiredExperienceSelectionPolicy.choose_one:
        if not set(requirement.candidate_place_ids) <= place_ids:
            raise RequiredExperienceGraphValidationError("candidate place is not evidence-backed")
        if len(activities) != 1:
            raise RequiredExperienceGraphValidationError("choose_one candidates must share one activity")
    elif policy is RequiredExperienceSelectionPolicy.open_candidate:
        if requirement.activity_id not in activities:
            raise RequiredExperienceGraphValidationError("open candidate activity is not evidence-backed")
    return requirement


def _claims(evidence: TripResearchBundle | GraphCandidateCatalog) -> list[GraphEvidenceClaim]:
    if isinstance(evidence, TripResearchBundle):
        conflicted = {item.claim.claimId for item in evidence.conflictedExperiences}
        unknown = {item.claimId for item in evidence.unknowns}
        if conflicted or unknown:
            raise RequiredExperienceGraphValidationError("conflicted or unknown claims are not eligible")
        return [item.claim for item in evidence.eligibleExperiences if item.fit.status is CheckStatus.SUPPORTED and not item.fit.hasHardConflict]
    return _synthetic_claims_from_catalog(evidence)


def _synthetic_claims_from_catalog(
    catalog: GraphCandidateCatalog,
) -> list[GraphEvidenceClaim]:
    """Build synthetic ``GraphEvidenceClaim`` rows from a bounded catalog.

    The catalog only carries the IDs that survived the projection step. We
    rebuild minimal claim entities with the activity/anchor/source fields that
    the validator helpers need, while keeping the validation graph-bounded.

    Each catalog ``claim_id`` corresponds to one anchor Place in the source
    ranking. We emit one synthetic claim per ``claim_id`` that exposes its
    corresponding anchor. When the catalog only has anchor Places (no claim
    IDs), the first anchor itself becomes the claim identifier so that
    validators still receive a populated ``anchorPlace.id``.
    """

    claims: list[GraphEvidenceClaim] = []
    for candidate in catalog.candidates:
        candidate_evidence = [
            EdgeEvidence(source=source, recommendations=[])
            for source in candidate.source_refs
            if source
        ]
        anchors = list(candidate.anchor_place_ids) or list(candidate.place_ids)
        if not anchors:
            continue
        activity_id = candidate.activity_id
        activity_entity = (
            _synthetic_entity(activity_id, "Activity") if activity_id else None
        )
        claim_ids = list(candidate.claim_ids)
        if not claim_ids:
            claim_ids = list(anchors)
        for claim_id, anchor_id in zip(claim_ids, anchors, strict=False):
            subject = _synthetic_entity(anchor_id, "TravelPlace")
            object_entity = (
                activity_entity
                if activity_entity is not None
                else _synthetic_entity(anchor_id, "TravelPlace")
            )
            predicate = (
                "OFFERS_ACTIVITY"
                if activity_id is not None
                else "SPECIAL_EXPERIENCE"
            )
            claims.append(
                GraphEvidenceClaim.model_construct(
                    claimId=claim_id,
                    subject=subject,
                    predicate=predicate,
                    object=object_entity,
                    path=[],
                    anchorPlace=subject,
                    activity=activity_entity,
                    recommendations=[],
                    evidence=candidate_evidence,
                    trust="SOURCE_BACKED",
                    inferenceSource=None,
                    warnings=[],
                )
            )
    return claims


def _synthetic_entity(entity_id: str | None, entity_type: str) -> object:
    return _EntitySummaryStub(id=entity_id, name=entity_id or "", type=entity_type, status="verified")


class _EntitySummaryStub:
    """Minimal duck-typed entity matching the validator's expectations."""

    __slots__ = ("id", "name", "type", "status")

    def __init__(self, *, id: str, name: str, type: str, status: str) -> None:
        self.id = id
        self.name = name
        self.type = type
        self.status = status


validate_required_experiences = validate_required_experience
