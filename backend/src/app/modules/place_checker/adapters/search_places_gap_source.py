from app.modules.place_checker.enums import RetrievalSourceKind
from app.modules.place_checker.errors import (
    CandidateSourceError,
    CandidateSourceTimeout,
)
from app.modules.place_checker.ports import NamedPlaceSearchTool
from app.modules.place_checker.retrieval_contract import (
    RetrievalEvidence,
    TargetedRetrievalQuery,
)
from app.shared.tools.search_places import AdministrativeArea, PlaceSearchRequest
from app.shared.tools.search_places.scoring import text_similarity


class SearchPlacesGapSource:
    """Adapts the shared search_places tool to targeted gap retrieval."""

    def __init__(
        self,
        search_tool: NamedPlaceSearchTool,
        *,
        provider_name: str,
        source_kind: RetrievalSourceKind,
        max_anchor_queries: int | None = None,
    ) -> None:
        self.search_tool = search_tool
        self.provider_name = provider_name
        self.source_kind = source_kind
        self.max_anchor_queries = (
            max(1, max_anchor_queries) if max_anchor_queries is not None else None
        )

    async def search(
        self,
        query: TargetedRetrievalQuery,
    ) -> list[RetrievalEvidence]:
        anchor_ids = query.anchor_place_ids or [None]
        if self.max_anchor_queries is not None:
            anchor_ids = anchor_ids[: self.max_anchor_queries]
        elif self.source_kind == RetrievalSourceKind.external:
            # One browser lookup is enough for a discovery gap. Trying every
            # anchor multiplies Playwright launches without improving locality,
            # because the external query already includes the ADM scope.
            anchor_ids = anchor_ids[:1]
        matches = []
        seen: set[str] = set()
        provider_errors = 0
        timeouts = 0
        for anchor_id in anchor_ids:
            result = await self.search_tool.search(
                PlaceSearchRequest(
                    query=query.query_text,
                    input_adm=AdministrativeArea(
                        adm_id=query.adm_id,
                        name=query.adm_name,
                        country_code=query.country_code,
                    ),
                    search_mode="requirement",
                    place_type_hint=query.category_hint,
                    anchor_place_id=anchor_id,
                    top_k=min(60, max(5, query.limit)),
                    allow_external_fallback=(
                        self.source_kind == RetrievalSourceKind.external
                    ),
                    provider_scope=(
                        "external"
                        if self.source_kind == RetrievalSourceKind.external
                        else "knowledge_graph"
                    ),
                )
            )
            if result.status == "provider_error":
                provider_errors += 1
                if any(
                    attempt.provider == self.provider_name
                    and attempt.outcome == "timeout"
                    for attempt in result.provider_attempts
                ):
                    timeouts += 1
                continue
            for match in result.top_matches:
                if match.provider != self.provider_name or match.rejection_reasons:
                    continue
                if not self._is_relevant(match, query):
                    continue
                key = match.place_id or match.provider_id or match.name
                if key in seen:
                    continue
                seen.add(key)
                matches.append(match)
            # Do not stop after the first keyword matches. The provider may
            # return graph-linked places later in its wider window.
        if not matches and provider_errors == len(anchor_ids):
            if timeouts == len(anchor_ids):
                raise CandidateSourceTimeout()
            raise CandidateSourceError()
        relation_matches = [
            match
            for match in matches
            if match.relationship_score > 0
            or self._matches_relation_terms(match.tags, query.relation_terms)
        ]
        fallback_matches = [
            match
            for match in matches
            if match not in relation_matches
        ]
        selected_matches = (relation_matches + fallback_matches)[: query.limit]
        return [
            RetrievalEvidence(
                provider=self.provider_name,
                source_kind=self.source_kind,
                provider_id=match.provider_id,
                entity_id=(
                    match.place_id
                    if self.source_kind != RetrievalSourceKind.external
                    else None
                ),
                name=match.name,
                adm_id=query.adm_id,
                category=match.canonical_type,
                experience_type=next(
                    (
                        tag.split(":", 1)[1]
                        for tag in match.tags
                        if tag.startswith("experience:")
                    ),
                    None,
                ),
                address=match.address,
                coordinates=match.coordinates,
                tags=[
                    *match.tags,
                    *(
                        ["relationship:pending"]
                        if any(
                            relationship.get("status") == "pending"
                            for relationship in match.relationship_evidence
                        )
                        else []
                    ),
                    *([
                        "retrieval:relation"
                    ] if match.relationship_score > 0 else ["retrieval:keyword_fallback"]),
                ],
                confidence=match.score,
                relationship_score=match.relationship_score,
                relationships=match.relationship_evidence,
                fetched_at=match.fetched_at,
                is_verified=match.verification_status == "verified",
            )
            for match in selected_matches
        ]

    @staticmethod
    def _matches_relation_terms(tags: list[str], terms: list[str]) -> bool:
        if not terms:
            return True
        relation_tags = [
            tag.split(":", 1)[1]
            for tag in tags
            if tag.startswith(("experience:", "style:"))
        ]
        return any(
            text_similarity(term, tag) >= 0.28
            for term in terms
            for tag in relation_tags
        )

    @classmethod
    def _is_relevant(cls, match, query: TargetedRetrievalQuery) -> bool:
        if match.score < 0.55:
            return False
        name_score = match.score_components.get("nameSimilarity", 0)
        if match.relationship_score > 0:
            return not query.relation_terms or cls._matches_relation_terms(
                match.tags, query.relation_terms
            )
        return name_score >= 0.35
