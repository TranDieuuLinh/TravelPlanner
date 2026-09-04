import asyncio

from app.modules.place_checker.adapters import (
    CachingAdmResolver,
    CachingNamedPlaceSearchTool,
    CachingPlaceMetadataRepository,
)
from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    PlaceCandidateInput,
    SourcePlaceEvidence,
)
from app.modules.place_checker.enums import EvidenceOrigin
from app.modules.place_checker.resolution.service import EntityResolutionService
from app.modules.place_checker.resolution.contract import PlaceMetadata
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.shared.tools.search_places import (
    AdministrativeArea,
    PlaceSearchRequest,
    PlaceSearchResult,
)


class CountingAdmResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, input_name):
        self.calls += 1
        return AdmResolution(
            input_name=input_name,
            status=AdmResolutionStatus.resolved,
            adm_id="adm1_vn_ha_noi",
            canonical_name="Hà Nội",
            country_code="VN",
            region_key="vn,ha_noi",
        )


class CountingSearchTool:
    def __init__(self) -> None:
        self.calls = 0

    async def search(self, request):
        self.calls += 1
        return PlaceSearchResult(
            status="unresolved",
            query=request.query,
            normalized_query=request.query.casefold(),
            search_mode=request.search_mode,
            resolution_reason="not_found",
        )


class CountingMetadataRepository:
    def __init__(self) -> None:
        self.calls = []

    async def get_many(self, place_ids):
        self.calls.append(place_ids)
        return {
            place_id: PlaceMetadata(place_id=place_id)
            for place_id in place_ids
        }


class ConcurrencySearchTool:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0

    async def search(self, request):
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        return PlaceSearchResult(
            status="unresolved",
            query=request.query,
            normalized_query=request.query.casefold(),
            search_mode=request.search_mode,
            resolution_reason="not_found",
        )


class BatchSearchTool:
    def __init__(self) -> None:
        self.batch_sizes = []

    async def search_many(self, requests):
        self.batch_sizes.append(len(requests))
        return [
            PlaceSearchResult(
                status="unresolved",
                query=request.query,
                normalized_query=request.query.casefold(),
                search_mode=request.search_mode,
                resolution_reason="not_found",
            )
            for request in requests
        ]


def search_request() -> PlaceSearchRequest:
    return PlaceSearchRequest(
        query="museum",
        input_adm=AdministrativeArea(
            adm_id="adm1_vn_ha_noi",
            name="Hà Nội",
            country_code="VN",
        ),
    )


def candidate(index: int) -> PlaceCandidateInput:
    return PlaceCandidateInput(
        name=f"Place {index}",
        confidence=0.9,
        source_places=[
            SourcePlaceEvidence(
                origin=EvidenceOrigin.input,
                evidence_type="test",
                evidence=f"Visit Place {index}",
            )
        ],
    )


def test_adm_and_search_cache_avoid_duplicate_provider_calls() -> None:
    adm = CountingAdmResolver()
    cached_adm = CachingAdmResolver(adm)
    search = CountingSearchTool()
    cached_search = CachingNamedPlaceSearchTool(search)

    async def run():
        await cached_adm.resolve("Hanoi")
        await cached_adm.resolve("hanoi")
        await cached_search.search(search_request())
        await cached_search.search(search_request())

    asyncio.run(run())

    assert adm.calls == 1
    assert search.calls == 1


def test_metadata_cache_only_loads_missing_ids() -> None:
    repository = CountingMetadataRepository()
    cached = CachingPlaceMetadataRepository(repository)

    async def run():
        await cached.get_many(["a", "b"])
        return await cached.get_many(["b", "c"])

    result = asyncio.run(run())

    assert repository.calls == [["a", "b"], ["c"]]
    assert set(result) == {"b", "c"}


def test_entity_resolution_respects_concurrency_bound() -> None:
    search = ConcurrencySearchTool()
    service = EntityResolutionService(search, max_concurrency=3)

    result = asyncio.run(
        service.resolve_all(
            [candidate(index) for index in range(12)],
            analysis_context(),
        )
    )

    assert len(result.candidates) == 12
    assert search.maximum == 3


def test_entity_resolution_groups_fifty_candidates_into_five_batches() -> None:
    search = BatchSearchTool()
    service = EntityResolutionService(search, max_concurrency=2)

    result = asyncio.run(
        service.resolve_all(
            [candidate(index) for index in range(50)],
            analysis_context(),
        )
    )

    assert len(result.candidates) == 50
    assert search.batch_sizes == [10, 10, 10, 10, 10]
