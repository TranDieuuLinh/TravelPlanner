"""Read-only place search boundary for the InformationFinder agent."""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Mapping, Protocol, Sequence

from app.modules.knowledge_graph.place_search import KnowledgeGraphPlaceMatch

if TYPE_CHECKING:
    from app.modules.places.resolver import GoogleMapsSearchClient

from .schema import InformationCandidate, InformationResult, InformationSource

logger = logging.getLogger(__name__)


class PlaceSearchReader(Protocol):
    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> InformationResult: ...


class PlaceSearchProvider(Protocol):
    provider_name: str

    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Mapping[str, Any]]: ...


class GoogleMapsPlaceSearchProvider:
    """Adapt the existing scraper client to the read provider contract."""

    provider_name = "google_maps_scraper"

    def __init__(self, client: GoogleMapsSearchClient) -> None:
        self.client = client

    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        del filters
        return await self.client.search(query, region=destination or None, limit=top_k)


class InformationFinderReader:
    """Graph-first, read-only place search with an external fallback."""

    def __init__(
        self,
        graph_repository: Any | None = None,
        provider: PlaceSearchProvider | None = None,
        *,
        clock: Any = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.graph_repository = graph_repository
        self.provider = provider
        self._clock = clock

    async def search(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None = None,
    ) -> InformationResult:
        if not 1 <= top_k <= 10:
            raise ValueError("top_k must be between 1 and 10")
        cleaned = query.strip()
        if not cleaned:
            return InformationResult(
                kind="empty",
                message="A place search query is required.",
            )

        warnings: list[str] = []
        graph_candidates = self._graph_candidates(cleaned, destination, top_k, filters)
        candidates = list(graph_candidates)
        if len(candidates) < top_k and self.provider is not None:
            try:
                provider_results = await self.provider.search(
                    cleaned, destination, top_k, filters
                )
                candidates = _merge_candidates(
                    candidates,
                    [self._provider_candidate(item) for item in provider_results],
                    limit=top_k,
                )
            except Exception:
                provider_name = getattr(self.provider, "provider_name", "place_provider")
                warnings.append(f"provider_search_failed:{provider_name}")
                logger.warning("InformationFinder place provider failed", exc_info=True)

        return InformationResult(
            kind="candidates" if candidates else "empty",
            message=("Choose a place candidate." if candidates else "No places found."),
            candidates=candidates,
            needs_user_choice=bool(candidates),
            warnings=warnings,
        )

    def _graph_candidates(
        self,
        query: str,
        destination: str | None,
        top_k: int,
        filters: Mapping[str, object] | None,
    ) -> list[InformationCandidate]:
        del filters
        if self.graph_repository is None:
            return []
        records = self.graph_repository.search(query, destination, limit=top_k)
        return [self._graph_candidate(record) for record in records]

    def _graph_candidate(self, record: KnowledgeGraphPlaceMatch) -> InformationCandidate:
        identity = str(record.entity_id)
        fetched_at = _timestamp(getattr(record, "source_fetched_at", None), self._clock)
        return InformationCandidate(
            candidateId=f"knowledge_graph:{identity}",
            placeId=identity,
            source=InformationSource.knowledge_graph,
            sourceRefs=[f"knowledge_graph:{identity}"],
            candidateEntityIds=[identity],
            latitude=record.latitude,
            longitude=record.longitude,
            confidence=1.0 if record.status == "verified" else 0.75,
            isVerified=record.status == "verified",
            fetchedAt=fetched_at,
        )

    def _provider_candidate(self, result: Mapping[str, Any]) -> InformationCandidate:
        provider = getattr(self.provider, "provider_name", "external_provider")
        identity = _text(result.get("place_id") or result.get("data_id"))
        name = _text(result.get("title") or result.get("name")) or "unknown"
        stable_identity = identity or _identity_key(name, result)
        lat = _number(result.get("latitude") or result.get("y"))
        lng = _number(result.get("longitude") or result.get("x"))
        return InformationCandidate(
            candidateId=f"{provider}:{stable_identity}",
            placeId=identity,
            source=InformationSource.external_provider,
            sourceRefs=[f"{provider}:{stable_identity}"],
            latitude=lat,
            longitude=lng,
            confidence=0.5,
            isVerified=False,
            fetchedAt=_timestamp(result.get("fetched_at") or result.get("fetchedAt"), self._clock),
        )


def _merge_candidates(
    primary: list[InformationCandidate],
    fallback: list[InformationCandidate],
    *,
    limit: int,
) -> list[InformationCandidate]:
    merged: list[InformationCandidate] = []
    seen: set[str] = set()
    for candidate in [*primary, *fallback]:
        keys = {key for key in (candidate.place_id, *candidate.source_refs) if key}
        if not keys:
            keys = {candidate.candidate_id}
        if seen.intersection(keys):
            continue
        merged.append(candidate)
        seen.update(keys)
        if len(merged) >= limit:
            break
    return merged


def _identity_key(name: str, result: Mapping[str, Any]) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().casefold()
    lat = _number(result.get("latitude") or result.get("y"))
    lng = _number(result.get("longitude") or result.get("x"))
    return f"{text}:{lat}:{lng}"


def _text(value: Any) -> str | None:
    value = str(value).strip() if value is not None else ""
    return value or None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any, clock: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return clock()
