"""Experience discovery research tool for Knowledge Graph.

This module provides read-only operations for discovering special experiences
from the knowledge graph.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING

from app.modules.knowledge_graph.research.repository import (
    KnowledgeGraphResearchRepository,
)
from app.modules.knowledge_graph.research.schema import (
    EdgeEvidence,
    EntitySummary,
    ExperienceDiscoveryInput,
    GraphEvidenceBundle,
    GraphEvidenceClaim,
    GraphSnapshot,
    Recommendation,
    RecommendationPriority,
    SpecialExperienceCandidate,
    SpecialExperienceCatalog,
    TrustLevel,
    UnknownClaim,
)

if TYPE_CHECKING:
    pass


def _generate_claim_id(
    subject_id: str,
    predicate: str,
    object_id: str,
    path_segment: str | None = None,
) -> str:
    """Generate a stable deterministic claim ID."""
    components = [subject_id, predicate, object_id]
    if path_segment:
        components.append(path_segment)

    content = "|".join(sorted(components))
    hash_digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
    return f"clm_{hash_digest}"


def _rank_claim(claim: GraphEvidenceClaim) -> tuple:
    """Compute sort key for deterministic claim ordering.

    Ranking order:
    1. trust (verified > source_backed > inferred)
    2. highest priority (must > recommended > optional)
    3. name (alphabetical)
    4. claim ID (stable)
    """
    trust_order = {
        TrustLevel.VERIFIED: 0,
        TrustLevel.SOURCE_BACKED: 1,
        TrustLevel.INFERRED: 2,
    }

    priority_order = {
        "must": 0,
        "recommended": 1,
        "optional": 2,
    }

    highest_priority = "optional"
    if claim.recommendations:
        priorities = [r.priority.value for r in claim.recommendations]
        for p in priorities:
            if priority_order.get(p, 99) < priority_order.get(highest_priority, 99):
                highest_priority = p

    return (
        trust_order.get(claim.trust.value, 99),
        priority_order.get(highest_priority, 99),
        claim.object.name.lower(),
        claim.claimId,
    )


def _least_trusted(*levels: TrustLevel) -> TrustLevel:
    order = {
        TrustLevel.VERIFIED: 0,
        TrustLevel.SOURCE_BACKED: 1,
        TrustLevel.INFERRED: 2,
    }
    return max(levels, key=order.__getitem__)


def build_special_experience_catalog(
    claims: list[GraphEvidenceClaim],
    limit: int = 30,
) -> SpecialExperienceCatalog:
    """Project only Activity-backed SPECIAL_EXPERIENCE claims.

    OFFERS_ACTIVITY/LOCATED_IN claims are useful only as anchors for an Activity
    already established by SPECIAL_EXPERIENCE. This prevents ordinary meals or
    Place names from becoming main experiences without an explicit claim.
    """
    grouped: dict[str, list[GraphEvidenceClaim]] = {}
    special_activity_ids: set[str] = set()
    warnings: list[str] = []
    for claim in claims:
        activity_id = claim.activity.id if claim.activity else None
        if not activity_id:
            continue
        if claim.predicate == "SPECIAL_EXPERIENCE" and claim.object.type in {
            "Activity", "Event", "Tour", "Workshop", "Class",
        }:
            special_activity_ids.add(activity_id)
            grouped.setdefault(activity_id, []).append(claim)

    for claim in claims:
        activity_id = claim.activity.id if claim.activity else None
        if (
            activity_id
            and activity_id in special_activity_ids
            and claim.predicate in {"LOCATED_IN", "OFFERS_ACTIVITY"}
        ):
            grouped.setdefault(activity_id, []).append(claim)

    candidates: list[SpecialExperienceCandidate] = []
    priority_order = {
        RecommendationPriority.MUST: 0,
        RecommendationPriority.RECOMMENDED: 1,
        RecommendationPriority.OPTIONAL: 2,
    }
    for activity_id, activity_claims in grouped.items():
        ordered = sorted(activity_claims, key=lambda claim: (claim.claimId, claim.path))
        primary = next(
            claim for claim in ordered if claim.predicate == "SPECIAL_EXPERIENCE"
        )
        recommendations = [
            recommendation
            for claim in ordered
            for recommendation in claim.recommendations
        ]
        recommendation = min(
            recommendations,
            key=lambda item: (priority_order[item.priority], item.model_dump_json()),
            default=None,
        )
        if recommendation is not None:
            # Keep the strongest priority while filling timing from another
            # evidence edge when the strongest recommendation is untimed.
            time_slots = next(
                (item.timeSlots for item in recommendations if item.timeSlots),
                recommendation.timeSlots,
            )
            visit_minutes = recommendation.recommendedVisitMinutes
            if visit_minutes is None:
                visit_minutes = next(
                    (
                        item.recommendedVisitMinutes
                        for item in recommendations
                        if item.recommendedVisitMinutes is not None
                    ),
                    None,
                )
            if time_slots != recommendation.timeSlots or (
                visit_minutes != recommendation.recommendedVisitMinutes
            ):
                recommendation = recommendation.model_copy(
                    update={
                        "timeSlots": list(time_slots),
                        "recommendedVisitMinutes": visit_minutes,
                    }
                )
        place_ids = sorted({
            place.id
            for claim in ordered
            for place in ([claim.anchorPlace] if claim.anchorPlace else [])
        })
        sources = sorted({
            evidence.source
            for claim in ordered
            for evidence in claim.evidence
            if evidence.source
        })
        if not sources:
            warnings.append(
                f"CATALOG_CLAIM_WITHOUT_SOURCE: excluded Activity {activity_id}"
            )
            continue
        candidates.append(SpecialExperienceCandidate(
            claimIds=[claim.claimId for claim in ordered],
            placeIds=place_ids,
            anchorPlaceIds=place_ids,
            activityId=activity_id,
            predicate=primary.predicate,
            path=primary.path,
            edgeEvidence=[evidence for claim in ordered for evidence in claim.evidence],
            sourceRefs=sources,
            recommendation=recommendation,
            trust=max((claim.trust for claim in ordered), key=lambda level: {
                TrustLevel.VERIFIED: 0,
                TrustLevel.SOURCE_BACKED: 1,
                TrustLevel.INFERRED: 2,
            }[level]),
            warnings=list(dict.fromkeys(
                warning for claim in ordered for warning in claim.warnings
            )),
        ))

    candidates.sort(key=lambda candidate: (candidate.activity_id, candidate.claim_ids))
    if len(candidates) > limit:
        warnings.append(f"CATALOG_LIMIT_APPLIED: limited to {limit} candidates")
    return SpecialExperienceCatalog(candidates=candidates[:limit], warnings=warnings)


def kg_discover_experiences(
    repo: KnowledgeGraphResearchRepository,
    input_data: ExperienceDiscoveryInput,
) -> GraphEvidenceBundle:
    """Discover special experiences from the knowledge graph.

    This tool traverses schema-v7 paths to discover experiences:
    - LocationEntity → SPECIAL_EXPERIENCE → Activity
    - LocationEntity → SPECIAL_EXPERIENCE → Activity → TARGETS_PLACE → Place
    - Area ← LOCATED_IN ← Place → OFFERS_ACTIVITY → Activity

    Args:
        repo: The research repository (read-only)
        input_data: Input containing scope and filtering parameters

    Returns:
        GraphEvidenceBundle with claims, unknowns, warnings, and snapshot
    """
    warnings: list[str] = []
    unknowns: list[UnknownClaim] = []
    all_claims: list[GraphEvidenceClaim] = []
    seen_claim_keys: set[str] = set()

    # Resolve destination if provided
    root_area_id = input_data.rootAreaId
    if input_data.destination and not root_area_id:
        root_area = repo.resolve_area_by_name(input_data.destination)
        if root_area is None:
            return GraphEvidenceBundle(
                claims=[],
                unknowns=[UnknownClaim(
                    query=f"destination:{input_data.destination}",
                    reason="Could not resolve destination to an Area entity",
                )],
                warnings=["DESTINATION_NOT_FOUND: Resolve scope first"],
                graphSnapshot=GraphSnapshot(timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
        root_area_id = root_area.id

    if not root_area_id:
        return GraphEvidenceBundle(
            claims=[],
            unknowns=[UnknownClaim(
                query="scope",
                reason="Neither rootAreaId nor destination provided",
            )],
            warnings=["SCOPE_REQUIRED: Provide rootAreaId or destination"],
            graphSnapshot=GraphSnapshot(timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ")),
        )

    # Get all area IDs in scope (no N+1: single query for descendants)
    area_ids = repo.get_scope_area_ids(root_area_id)

    if not area_ids:
        return GraphEvidenceBundle(
            claims=[],
            unknowns=[UnknownClaim(
                query=f"area:{root_area_id}",
                reason="Area not found in graph",
            )],
            warnings=["AREA_NOT_FOUND"],
            graphSnapshot=GraphSnapshot(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                areaIds=[root_area_id],
            ),
        )

    # Batch fetch all entities we'll need (no N+1)
    all_place_ids: set[str] = set()
    all_activity_ids: set[str] = set()

    # Path 1: LocationEntity → SPECIAL_EXPERIENCE → Activity. Selected Places
    # are valid LocationEntity sources, but private notes never cross this API.
    location_ids = list(dict.fromkeys([
        *area_ids,
        *(input_data.selectedPlaceIds or []),
    ]))
    se_to_activity_rels = repo.query_special_experiences_in_scope(location_ids)
    for rel in se_to_activity_rels:
        all_activity_ids.add(rel.to_entity_id)

    # Optional direct anchors: Activity → TARGETS_PLACE → Place.
    target_rels = repo.query_activity_targets_place(list(all_activity_ids))
    if input_data.selectedPlaceIds:
        selected_ids = set(input_data.selectedPlaceIds)
        target_rels = [
            rel for rel in target_rels if rel.to_entity_id in selected_ids
        ]
    for rel in target_rels:
        all_place_ids.add(rel.to_entity_id)

    # Path 4: Area ← LOCATED_IN ← Place → OFFERS_ACTIVITY → Activity
    chained_li_offers = repo.query_located_in_place_offers_activity(area_ids)
    for li_rel, offers_rel in chained_li_offers:
        all_place_ids.add(li_rel.from_entity_id)
        all_activity_ids.add(offers_rel.to_entity_id)

    # Collect selected place IDs if provided
    if input_data.selectedPlaceIds:
        all_place_ids.update(input_data.selectedPlaceIds)

    # Batch fetch all entities (no N+1: single query for all)
    all_entity_ids = list(set(area_ids) | all_place_ids | all_activity_ids)
    entities_by_id = repo.get_entities_by_ids(all_entity_ids)

    # Build claims from each path

    targets_by_activity: dict[str, list] = {}
    for target_rel in target_rels:
        targets_by_activity.setdefault(target_rel.from_entity_id, []).append(target_rel)

    # Paths 1-2: direct special Activity, optionally anchored by TARGETS_PLACE.
    for rel in se_to_activity_rels:
        subject = entities_by_id.get(rel.from_entity_id)
        obj = entities_by_id.get(rel.to_entity_id)
        if not subject or not obj:
            continue

        trust, inference_source = repo._determine_trust(subject, rel.source)
        recs, rec_trust, rec_warnings = repo._parse_recommendations(
            rel.recommendations, rel.source
        )

        if not input_data.includeInferred and trust == TrustLevel.INFERRED:
            continue

        base_evidence = EdgeEvidence(
            edgeId=rel.id,
            source=rel.source,
            recommendations=recs,
            propertyProvenance=(
                rel.source
                if rel.source and rel.source.startswith("inference:")
                else None
            ),
        )
        anchors = targets_by_activity.get(obj.id) or [None]
        for target_rel in anchors:
            claim_trust = trust
            claim_inference_source = inference_source
            place = (
                entities_by_id.get(target_rel.to_entity_id)
                if target_rel is not None
                else None
            )
            if target_rel is not None and place is None:
                continue
            evidence = [base_evidence]
            path = [subject.id, rel.relationship_type, obj.id]
            if target_rel is not None and place is not None:
                target_trust, target_inference_source = repo._determine_trust(
                    obj,
                    target_rel.source,
                )
                claim_trust = _least_trusted(trust, target_trust)
                if target_trust is TrustLevel.INFERRED:
                    claim_inference_source = target_inference_source
                evidence.append(
                    EdgeEvidence(
                        edgeId=target_rel.id,
                        source=target_rel.source,
                        recommendations=[],
                        propertyProvenance=(
                            target_rel.source
                            if target_rel.source
                            and target_rel.source.startswith("inference:")
                            else None
                        ),
                    )
                )
                path.extend(["TARGETS_PLACE", place.id])
            claim = GraphEvidenceClaim(
                claimId=_generate_claim_id(
                    subject.id,
                    rel.relationship_type,
                    obj.id,
                    place.id if place is not None else None,
                ),
                subject=repo.get_entity_summary(subject),
                predicate=rel.relationship_type,
                object=repo.get_entity_summary(obj),
                path=path,
                anchorPlace=(
                    repo.get_entity_summary(place) if place is not None else None
                ),
                activity=repo.get_entity_summary(obj),
                recommendations=recs,
                evidence=evidence,
                trust=claim_trust,
                inferenceSource=claim_inference_source,
                warnings=list(rec_warnings),
            )
            dedupe_key = f"{subject.id}|{obj.id}|{place.id if place else '-'}"
            if dedupe_key not in seen_claim_keys:
                seen_claim_keys.add(dedupe_key)
                all_claims.append(claim)

    # Path 4: Area ← LOCATED_IN ← Place → OFFERS_ACTIVITY → Activity
    for li_rel, offers_rel in chained_li_offers:
        place = entities_by_id.get(li_rel.from_entity_id)
        area = entities_by_id.get(li_rel.to_entity_id)
        activity = entities_by_id.get(offers_rel.to_entity_id)
        if not area or not place or not activity:
            continue

        if input_data.selectedPlaceIds and place.id not in input_data.selectedPlaceIds:
            continue

        all_recs: list[Recommendation] = []
        all_evidence: list[EdgeEvidence] = []
        claim_warnings: list[str] = []

        offers_recs, _, offers_warnings = repo._parse_recommendations(
            offers_rel.recommendations, offers_rel.source
        )
        all_recs.extend(offers_recs)
        claim_warnings.extend(offers_warnings)

        # LOCATED_IN edges typically have no recommendations (per ADR-016)
        li_evidence = EdgeEvidence(
            edgeId=li_rel.id,
            source=li_rel.source,
            recommendations=[],
        )
        all_evidence.append(li_evidence)

        offers_evidence = EdgeEvidence(
            edgeId=offers_rel.id,
            source=offers_rel.source,
            recommendations=offers_recs,
            propertyProvenance=offers_rel.source if offers_rel.source and offers_rel.source.startswith("inference:") else None,
        )
        all_evidence.append(offers_evidence)

        # Trust based on OFFERS_ACTIVITY edge
        offers_trust, inference_source = repo._determine_trust(place, offers_rel.source)
        combined_trust = offers_trust

        if not input_data.includeInferred and combined_trust == TrustLevel.INFERRED:
            continue

        claim = GraphEvidenceClaim(
            claimId=_generate_claim_id(area.id, "LOCATED_IN", place.id, activity.id),
            subject=repo.get_entity_summary(area),
            predicate="LOCATED_IN",
            object=repo.get_entity_summary(place),
            path=[area.id, "LOCATED_IN", place.id, "OFFERS_ACTIVITY", activity.id],
            anchorPlace=repo.get_entity_summary(place),
            activity=repo.get_entity_summary(activity),
            recommendations=all_recs,
            evidence=all_evidence,
            trust=combined_trust,
            inferenceSource=inference_source,
            warnings=claim_warnings,
        )

        dedupe_key = f"{place.id}|LOCATED_IN|{activity.id}|OFFERS_ACTIVITY"
        if dedupe_key not in seen_claim_keys:
            seen_claim_keys.add(dedupe_key)
            all_claims.append(claim)

    # Sort deterministically and apply limit
    all_claims.sort(key=_rank_claim)
    limited_claims = all_claims[:input_data.limit]

    return GraphEvidenceBundle(
        claims=limited_claims,
        unknowns=unknowns,
        warnings=warnings,
        graphSnapshot=GraphSnapshot(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            areaIds=area_ids,
            placeIds=list(all_place_ids)[:100],
            activityIds=list(all_activity_ids)[:100],
        ),
        catalog=build_special_experience_catalog(all_claims, input_data.limit),
    )
