from app.modules.place_checker.enums import RetrievalSourceKind
from app.modules.place_checker.errors import CandidateSourceError, CandidateSourceTimeout
from app.modules.place_checker.ports import NamedPlaceSearchTool
from app.modules.place_checker.retrieval_contract import (
    RetrievalEvidence,
    TargetedRetrievalQuery,
)
from app.shared.tools.search_places import AdministrativeArea, PlaceSearchRequest


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
                top_k=query.limit,
                allow_external_fallback=(
                    self.source_kind == RetrievalSourceKind.external
                ),
            )
        )
        if result.status == "provider_error":
            timed_out = any(
                attempt.provider == self.provider_name
                and attempt.outcome == "timeout"
                for attempt in result.provider_attempts
            )
            if timed_out:
                raise CandidateSourceTimeout()
            raise CandidateSourceError()
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
                tags=match.tags,
                confidence=match.score,
                fetched_at=match.fetched_at,
            )
            for match in result.top_matches
            if match.provider == self.provider_name
            and not match.rejection_reasons
        ]
