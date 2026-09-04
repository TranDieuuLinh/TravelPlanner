"""Identity grouping and verification for retrieved catalog candidates."""

from app.modules.place_checker.enums import RetrievalSourceKind, VerificationStatus
from app.modules.place_checker.retrieval.contract import (
    RetrievalEvidence,
    RetrievedCandidate,
    TargetedRetrievalQuery,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km, text_similarity


class RetrievalVerificationMixin:
    @classmethod
    def _verify(cls, evidence, query):
        groups: list[list[RetrievalEvidence]] = []
        for item in evidence:
            group = next(
                (group for group in groups if cls._same_place(group[0], item)),
                None,
            )
            (groups.append([item]) if group is None else group.append(item))
        candidates = [cls._candidate(group, query) for group in groups]
        conflicts = cls._conflicting_names(groups)
        candidates = [
            candidate.model_copy(
                update={
                    "verification_status": VerificationStatus.needs_review,
                    "planner_eligible": False,
                    "conflicts": [
                        *candidate.conflicts,
                        "provider_identity_conflict",
                    ],
                }
            )
            if normalize_text(candidate.canonical_name) in conflicts
            else candidate
            for candidate in candidates
        ]
        return sorted(
            candidates,
            key=lambda item: (
                not item.planner_eligible,
                -max(source.confidence for source in item.evidence),
                normalize_text(item.canonical_name),
            ),
        )

    @staticmethod
    def _candidate(
        evidence: list[RetrievalEvidence], query: TargetedRetrievalQuery
    ) -> RetrievedCandidate:
        representative = max(evidence, key=lambda item: item.confidence)
        linked_entity = next(
            (item.entity_id for item in evidence if item.entity_id), None
        )
        has_kg_link = any(
            item.entity_id
            and item.source_kind == RetrievalSourceKind.knowledge_graph
            and item.is_verified
            for item in evidence
        )
        external_providers = {
            item.provider
            for item in evidence
            if item.source_kind == RetrievalSourceKind.external
        }
        if not all(item.adm_id in {None, query.adm_id} for item in evidence):
            status = VerificationStatus.needs_review
        elif has_kg_link:
            status = VerificationStatus.verified_kg
        elif len(external_providers) >= 2:
            status = VerificationStatus.verified_external
        else:
            status = VerificationStatus.provisional
        metadata = next((item.metadata for item in evidence if item.metadata), None)
        key_source = linked_entity or ":".join(
            [
                normalize_text(representative.name),
                normalize_text(representative.adm_id or query.adm_id),
                normalize_text(representative.category),
            ]
        )
        return RetrievedCandidate(
            candidate_key=key_source[:300],
            gap_id=query.gap_id,
            gap_type=query.gap_type,
            gap_severity=query.severity,
            canonical_name=representative.name,
            place_id=linked_entity,
            adm_id=representative.adm_id or query.adm_id,
            region_key=representative.region_key,
            category=representative.category,
            pool_category=(
                query.gap_id.removeprefix("pool:")
                .removesuffix("_alternatives")
                .removesuffix("_candidates")
                if query.gap_id.startswith("pool:")
                else None
            ),
            experience_type=representative.experience_type,
            address=representative.address,
            coordinates=representative.coordinates,
            tags=list(dict.fromkeys(tag for item in evidence for tag in item.tags)),
            metadata=metadata,
            relationship_score=max(item.relationship_score for item in evidence),
            relationships=list(
                {
                    (
                        relation.relationship_type,
                        relation.from_entity_id,
                        relation.to_entity_id,
                    ): relation
                    for item in evidence
                    for relation in item.relationships
                }.values()
            ),
            verification_status=status,
            planner_eligible=status
            in {VerificationStatus.verified_kg, VerificationStatus.verified_external},
            evidence=evidence,
            warnings=(
                ["Mới có một nguồn ngoài; chưa được đưa vào Planner."]
                if status == VerificationStatus.provisional
                else []
            ),
        )

    @staticmethod
    def _same_place(left: RetrievalEvidence, right: RetrievalEvidence) -> bool:
        if left.entity_id and left.entity_id == right.entity_id:
            return True
        if left.provider == right.provider and left.provider_id == right.provider_id:
            return bool(left.provider_id)
        if text_similarity(left.name, right.name) < 0.88:
            return False
        if left.adm_id and right.adm_id and left.adm_id != right.adm_id:
            return False
        if (
            left.category
            and right.category
            and normalize_text(left.category) != normalize_text(right.category)
        ):
            return False
        if left.coordinates and right.coordinates:
            return distance_km(left.coordinates, right.coordinates) <= 0.5
        return bool(
            left.address
            and right.address
            and text_similarity(left.address, right.address) >= 0.7
        )

    @staticmethod
    def _conflicting_names(groups: list[list[RetrievalEvidence]]) -> set[str]:
        conflicts: set[str] = set()
        representatives = [group[0] for group in groups]
        for index, left in enumerate(representatives):
            for right in representatives[index + 1 :]:
                if normalize_text(left.name) != normalize_text(right.name):
                    continue
                if not left.adm_id or not right.adm_id or left.adm_id == right.adm_id:
                    conflicts.add(normalize_text(left.name))
        return conflicts

    @staticmethod
    def _verified_count(candidates: list[RetrievedCandidate]) -> int:
        return sum(candidate.planner_eligible for candidate in candidates)
