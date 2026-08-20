from hashlib import sha256

from app.modules.place_checker.contract import SourcePlaceEvidence, TripEvaluationContext
from app.modules.place_checker.enums import (
    EvidenceOrigin,
    IdentityResolutionStatus,
    SimilarityMethod,
    SourceTier,
    VerificationStatus,
)
from app.modules.place_checker.resolution.contract import (
    CatalogPlace,
    EnrichedIdentityPlace,
    PlaceMatchOption,
    PlaceMetadata,
    SimilarityComponents,
)
from app.modules.place_checker.scoring.contract import ScoredCandidate


class RetrievalCandidateProjector:
    def to_enriched_places(
        self,
        ranked: list[ScoredCandidate],
        context: TripEvaluationContext,
    ) -> tuple[
        list[EnrichedIdentityPlace],
        dict[str, VerificationStatus],
        dict[str, ScoredCandidate],
    ]:
        places: list[EnrichedIdentityPlace] = []
        verification: dict[str, VerificationStatus] = {}
        ranking: dict[str, ScoredCandidate] = {}
        for scored in ranked:
            candidate = scored.candidate
            place_id = candidate.place_id or self._external_id(candidate.candidate_key)
            if candidate.metadata is None:
                metadata = PlaceMetadata(
                    place_id=place_id,
                    coordinates=candidate.coordinates,
                    address=candidate.address,
                    category=candidate.category,
                    tags=self._tags(candidate),
                    relationships=candidate.relationships,
                )
            else:
                metadata = candidate.metadata.model_copy(
                    update={"tags": self._tags(candidate)}
                )
            if metadata.place_id != place_id:
                metadata = metadata.model_copy(update={"place_id": place_id})
            catalog = CatalogPlace(
                place_id=place_id,
                canonical_name=candidate.canonical_name,
                adm_id=candidate.adm_id,
                region_key=candidate.region_key,
                country_code=context.destination.country_code,
                address=candidate.address,
                category=candidate.category,
                coordinates=candidate.coordinates,
                provider_ids=[
                    item.provider_id
                    for item in candidate.evidence
                    if item.provider_id
                ],
                tags=self._tags(candidate),
                relationships=candidate.relationships,
            )
            option = PlaceMatchOption(
                place=catalog,
                method=SimilarityMethod.semantic,
                components=SimilarityComponents(
                    lexical_score=scored.components.intent_match,
                    semantic_score=scored.components.intent_match,
                    destination_score=1,
                    combined_score=scored.final_score,
                ),
                rank=scored.rank or 1,
                eligible_destination=True,
                reasons=["targeted_gap_retrieval"],
            )
            sources = [
                SourcePlaceEvidence(
                    origin=EvidenceOrigin.system,
                    evidence_type="verified_retrieval",
                    evidence=f"Normalized evidence from {item.provider}",
                    address_hint=item.address,
                )
                for item in candidate.evidence
            ]
            places.append(
                EnrichedIdentityPlace(
                    place_id=place_id,
                    canonical_name=candidate.canonical_name,
                    original_names=[candidate.canonical_name],
                    source_tier=SourceTier.system_suggested,
                    mandatory=False,
                    removable=True,
                    status=IdentityResolutionStatus.resolved,
                    identity_confidence=max(
                        item.confidence for item in candidate.evidence
                    ),
                    metadata=metadata,
                    source_places=sources,
                    match_options=[option],
                    warnings=candidate.warnings,
                )
            )
            verification[place_id] = candidate.verification_status
            ranking[place_id] = scored
        return places, verification, ranking

    @staticmethod
    def _external_id(candidate_key: str) -> str:
        digest = sha256(candidate_key.encode("utf-8")).hexdigest()[:24]
        return f"external_verified:{digest}"

    @staticmethod
    def _tags(candidate) -> list[str]:
        tags = list(candidate.tags)
        if candidate.pool_category:
            tags.append(f"pool_category:{candidate.pool_category}")
        return list(dict.fromkeys(tags))
