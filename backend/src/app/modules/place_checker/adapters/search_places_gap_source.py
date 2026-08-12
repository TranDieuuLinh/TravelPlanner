from app.modules.place_checker.enums import RetrievalSourceKind
from app.modules.place_checker.errors import CandidateSourceError, CandidateSourceTimeout
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
    ) -> None:
        self.search_tool = search_tool
        self.provider_name = provider_name
        self.source_kind = source_kind

    async def search(
        self,
        query: TargetedRetrievalQuery,
    ) -> list[RetrievalEvidence]:
        anchor_ids = query.anchor_place_ids or [None]
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
                    # Ask the shared tool for a wider relation-first window.
                    # The provider orders graph-linked candidates first; this
                    # leaves room for keyword fallbacks when the graph is sparse.
                    top_k=min(60, max(query.limit, query.limit * 3)),
                    allow_external_fallback=(
                        self.source_kind == RetrievalSourceKind.external
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
                    *([
                        "retrieval:relation"
                    ] if match.relationship_score > 0 else ["retrieval:keyword_fallback"]),
                ],
                confidence=match.score,
                relationship_score=match.relationship_score,
                fetched_at=match.fetched_at,
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
