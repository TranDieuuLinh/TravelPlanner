from typing import Protocol

from app.modules.place_checker.contract import AdmResolution
from app.modules.place_checker.enums import RetrievalSourceKind
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.modules.place_checker.retrieval_contract import (
    PromotionEvent,
    RetrievedCandidate,
    RetrievalEvidence,
    TargetedRetrievalQuery,
)
from app.shared.contracts.place import PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent
from app.shared.tools.search_places import PlaceSearchRequest, PlaceSearchResult


class AdmResolver(Protocol):
    async def resolve(self, input_name: str) -> AdmResolution: ...


class NamedPlaceSearchTool(Protocol):
    async def search(self, request: PlaceSearchRequest) -> PlaceSearchResult: ...


class PlaceMetadataRepository(Protocol):
    async def get_many(self, place_ids: list[str]) -> dict[str, PlaceMetadata]: ...


class GapCandidateSource(Protocol):
    provider_name: str
    source_kind: RetrievalSourceKind

    async def search(
        self,
        query: TargetedRetrievalQuery,
    ) -> list[RetrievalEvidence]: ...


class PromotionOutbox(Protocol):
    async def enqueue(self, event: PromotionEvent) -> bool: ...

    async def claim(self, limit: int) -> list[PromotionEvent]: ...

    async def mark_promoted(self, event_id: str, entity_id: str) -> None: ...

    async def mark_failed(self, event_id: str, error_code: str) -> None: ...


class PromotionCatalog(Protocol):
    async def find_duplicate(self, candidate: RetrievedCandidate) -> str | None: ...

    async def promote(self, candidate: RetrievedCandidate) -> str: ...


class PlaceCheckerMetricsSink(Protocol):
    async def record(
        self,
        metric: str,
        value: float,
        tags: dict[str, str],
    ) -> None: ...


class PlaceResolver(Protocol):
    async def resolve(
        self,
        candidate: PlaceCandidate,
        intent: TripIntent,
    ) -> VerifiedPlace | None: ...


class PlaceDiscovery(Protocol):
    async def discover(
        self,
        intent: TripIntent,
        limit: int,
    ) -> list[VerifiedPlace]: ...
