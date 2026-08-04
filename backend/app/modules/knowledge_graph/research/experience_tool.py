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


def kg_discover_experiences(
    repo: KnowledgeGraphResearchRepository,
    input_data: ExperienceDiscoveryInput,
) -> GraphEvidenceBundle:
    """Discover special experiences from the knowledge graph.

    This tool traverses multiple paths to discover experiences:
    - Area → SPECIAL_EXPERIENCE → Place
    - Area → SPECIAL_EXPERIENCE → Activity
    - Area → SPECIAL_EXPERIENCE → Place → OFFERS_ACTIVITY → Activity
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

    # Path 1: Area → SPECIAL_EXPERIENCE → Place
    se_to_place_rels = repo.query_special_experiences_in_scope(area_ids)
    for rel in se_to_place_rels:
        all_place_ids.add(rel.to_entity_id)

    # Path 2: Area → SPECIAL_EXPERIENCE → Activity
    se_to_activity_rels = repo.query_activities_in_scope(area_ids)
    for rel in se_to_activity_rels:
        all_activity_ids.add(rel.to_entity_id)

    # Path 3: Area → SPECIAL_EXPERIENCE → Place → OFFERS_ACTIVITY → Activity
    chained_se_offers = repo.query_special_experience_to_place_offers_activity(area_ids)
    for se_rel, offers_rel in chained_se_offers:
        all_place_ids.add(se_rel.to_entity_id)
        all_activity_ids.add(offers_rel.to_entity_id)

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

    # Path 1: Area → SPECIAL_EXPERIENCE → Place
    for rel in se_to_place_rels:
        subject = entities_by_id.get(rel.from_entity_id)
        obj = entities_by_id.get(rel.to_entity_id)
        if not subject or not obj:
            continue

        # Filter by selected places if specified
        if input_data.selectedPlaceIds and obj.id not in input_data.selectedPlaceIds:
            continue

        trust, inference_source = repo._determine_trust(subject, rel.source)
        recs, rec_trust, rec_warnings = repo._parse_recommendations(
            rel.recommendations, rel.source
        )

        # Filter inferred if requested
        if not input_data.includeInferred and trust == TrustLevel.INFERRED:
            continue

        # Build evidence
        evidence = [EdgeEvidence(
            edgeId=rel.id,
            source=rel.source,
            recommendations=recs,
            propertyProvenance=rel.source if rel.source and rel.source.startswith("inference:") else None,
        )]

        claim_warnings = list(rec_warnings)
        if trust == TrustLevel.INFERRED and inference_source:
            claim_warnings.append(f"Trust based on: {inference_source}")

        claim = GraphEvidenceClaim(
            claimId=_generate_claim_id(subject.id, rel.relationship_type, obj.id),
            subject=repo.get_entity_summary(subject),
            predicate=rel.relationship_type,
            object=repo.get_entity_summary(obj),
            path=[subject.id, rel.relationship_type, obj.id],
            recommendations=recs,
            evidence=evidence,
            trust=trust,
            inferenceSource=inference_source,
            warnings=claim_warnings,
        )

        # Dedupe: same target + recommendation
        dedupe_key = f"{obj.id}|{rel.relationship_type}"
        if dedupe_key not in seen_claim_keys:
            seen_claim_keys.add(dedupe_key)
            all_claims.append(claim)

    # Path 2: Area → SPECIAL_EXPERIENCE → Activity
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

        evidence = [EdgeEvidence(
            edgeId=rel.id,
            source=rel.source,
            recommendations=recs,
            propertyProvenance=rel.source if rel.source and rel.source.startswith("inference:") else None,
        )]

        claim_warnings = list(rec_warnings)

        claim = GraphEvidenceClaim(
            claimId=_generate_claim_id(subject.id, rel.relationship_type, obj.id),
            subject=repo.get_entity_summary(subject),
            predicate=rel.relationship_type,
            object=repo.get_entity_summary(obj),
            path=[subject.id, rel.relationship_type, obj.id],
            activity=repo.get_entity_summary(obj),
            recommendations=recs,
            evidence=evidence,
            trust=trust,
            inferenceSource=inference_source,
            warnings=claim_warnings,
        )

        dedupe_key = f"{obj.id}|{rel.relationship_type}"
        if dedupe_key not in seen_claim_keys:
            seen_claim_keys.add(dedupe_key)
            all_claims.append(claim)

    # Path 3: Area → SPECIAL_EXPERIENCE → Place → OFFERS_ACTIVITY → Activity
    for se_rel, offers_rel in chained_se_offers:
        area = entities_by_id.get(se_rel.from_entity_id)
        place = entities_by_id.get(se_rel.to_entity_id)
        activity = entities_by_id.get(offers_rel.to_entity_id)
        if not area or not place or not activity:
            continue

        if input_data.selectedPlaceIds and place.id not in input_data.selectedPlaceIds:
            continue

        # Combine recommendations from both edges
        all_recs: list[Recommendation] = []
        all_evidence: list[EdgeEvidence] = []
        claim_warnings: list[str] = []

        se_recs, _, se_warnings = repo._parse_recommendations(
            se_rel.recommendations, se_rel.source
        )
        all_recs.extend(se_recs)
        claim_warnings.extend(se_warnings)

        offers_recs, _, offers_warnings = repo._parse_recommendations(
            offers_rel.recommendations, offers_rel.source
        )
        all_recs.extend(offers_recs)
        claim_warnings.extend(offers_warnings)

        all_evidence.append(EdgeEvidence(
            edgeId=se_rel.id,
            source=se_rel.source,
            recommendations=se_recs,
            propertyProvenance=se_rel.source if se_rel.source and se_rel.source.startswith("inference:") else None,
        ))
        all_evidence.append(EdgeEvidence(
            edgeId=offers_rel.id,
            source=offers_rel.source,
            recommendations=offers_recs,
            propertyProvenance=offers_rel.source if offers_rel.source and offers_rel.source.startswith("inference:") else None,
        ))

        # Trust: take the lowest trust between the two edges
        se_trust, _ = repo._determine_trust(area, se_rel.source)
        offers_trust, offers_inference = repo._determine_trust(place, offers_rel.source)
        combined_trust = TrustLevel.INFERRED if (
            se_trust == TrustLevel.INFERRED or offers_trust == TrustLevel.INFERRED
        ) else (TrustLevel.SOURCE_BACKED if (
            se_trust == TrustLevel.SOURCE_BACKED or offers_trust == TrustLevel.SOURCE_BACKED
        ) else TrustLevel.VERIFIED)
        inference_source = offers_inference if offers_trust == TrustLevel.INFERRED else None

        if not input_data.includeInferred and combined_trust == TrustLevel.INFERRED:
            continue

        claim = GraphEvidenceClaim(
            claimId=_generate_claim_id(area.id, "SPECIAL_EXPERIENCE", place.id, activity.id),
            subject=repo.get_entity_summary(area),
            predicate="SPECIAL_EXPERIENCE",
            object=repo.get_entity_summary(place),
            path=[area.id, "SPECIAL_EXPERIENCE", place.id, "OFFERS_ACTIVITY", activity.id],
            anchorPlace=repo.get_entity_summary(place),
            activity=repo.get_entity_summary(activity),
            recommendations=all_recs,
            evidence=all_evidence,
            trust=combined_trust,
            inferenceSource=inference_source,
            warnings=claim_warnings,
        )

        dedupe_key = f"{place.id}|SPECIAL_EXPERIENCE|{activity.id}|OFFERS_ACTIVITY"
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
    )
