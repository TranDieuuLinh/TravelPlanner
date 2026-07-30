import asyncio
from typing import Any

from app.modules.places import resolver as resolver_module
from app.modules.places.resolver import (
    FallbackPlaceResolver,
    HerePlaceResolver,
    NominatimPlaceResolver,
    PlaceResolution,
    PlaceResolver,
)
from app.modules.plans import dependencies
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


class FakeNominatimResolver(NominatimPlaceResolver):
    def __init__(self, results: list[dict[str, Any]]) -> None:
        super().__init__(
            base_url="https://example.invalid",
            user_agent="VSF-Travel-Test/1.0",
        )
        self.results = results
        self.queries: list[str] = []

    async def _search(self, query: str) -> list[dict[str, Any]]:
        self.queries.append(query)
        return self.results


class FakeHereResolver(HerePlaceResolver):
    def __init__(self, results: list[dict[str, Any]]) -> None:
        super().__init__(
            base_url="https://example.invalid",
            api_key="test-key",
        )
        self.results = results
        self.queries: list[str] = []

    async def _search(
        self,
        query: str,
        *,
        search_region: str,
    ) -> list[dict[str, Any]]:
        self.queries.append(query)
        return self.results


class StaticPlaceResolver(PlaceResolver):
    def __init__(self, result: PlaceResolution) -> None:
        self.result = result
        self.calls = 0

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        self.calls += 1
        return self.result.model_copy(update={"candidate": candidate})


class ConcurrencyTrackingHereResolver(HerePlaceResolver):
    def __init__(
        self,
        *,
        unresolved_names: set[str] | None = None,
    ) -> None:
        super().__init__(
            base_url="https://example.invalid",
            api_key="test-key",
            max_concurrency=4,
        )
        self.unresolved_names = unresolved_names or set()
        self.active = 0
        self.max_active = 0

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(
            0.002 * (9 - int(candidate.name.rsplit(" ", 1)[-1]))
        )
        self.active -= 1
        if candidate.name in self.unresolved_names:
            return PlaceResolution(
                candidate=candidate,
                status="unresolved",
                resolutionReason="not_found",
                provider="here",
                name=candidate.name,
            )
        return PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="here",
            name=candidate.name,
            latitude="21.0285",
            longitude="105.8542",
        )


class ConcurrencyTrackingNominatimResolver(NominatimPlaceResolver):
    def __init__(self) -> None:
        super().__init__(
            base_url="https://example.invalid",
            user_agent="VSF-Travel-Test/1.0",
        )
        self.active = 0
        self.max_active = 0
        self.names: list[str] = []

    async def resolve(
        self,
        candidate: UnifiedPlaceCandidate,
        *,
        destination: str,
    ) -> PlaceResolution:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.names.append(candidate.name)
        await asyncio.sleep(0.001)
        self.active -= 1
        return PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="nominatim",
            name=candidate.name,
            latitude="21.0285",
            longitude="105.8542",
        )


def _candidate(name: str = "Mì Quảng Bà Mua") -> UnifiedPlaceCandidate:
    return UnifiedPlaceCandidate(
        name=name,
        category="food",
        sources=[{"type": "url", "url": "https://example.com/reel"}],
        confidence=0.8,
    )


def test_here_resolver_maps_discover_result_to_place_contract() -> None:
    resolver = FakeHereResolver(
        [
            {
                "title": "Mì Quảng Bà Mua",
                "id": "here:pds:place:704jx7ps-123",
                "resultType": "place",
                "address": {
                    "label": "Mì Quảng Bà Mua, Đà Nẵng, Việt Nam",
                    "countryCode": "VNM",
                    "countryName": "Việt Nam",
                    "city": "Đà Nẵng",
                    "district": "Hải Châu",
                },
                "position": {"lat": 16.0592, "lng": 108.2131},
                "categories": [
                    {
                        "id": "100-1000-0000",
                        "name": "Restaurant",
                        "primary": True,
                    }
                ],
            }
        ]
    )

    result = asyncio.run(
        resolver.resolve(_candidate(), destination="Đà Nẵng")
    )

    assert resolver.queries == ["Mì Quảng Bà Mua, Đà Nẵng"]
    assert result.status == "resolved"
    assert result.provider == "here"
    assert result.external_id == "here:pds:place:704jx7ps-123"
    assert result.country_code == "VNM"
    assert result.primary_area == "Hải Châu"
    assert str(result.latitude) == "16.0592"
    assert str(result.longitude) == "108.2131"
    assert result.attribution == "© HERE"


def test_here_resolver_rejects_a_locality_match_without_coordinates() -> None:
    resolver = FakeHereResolver(
        [
            {
                "title": "Hà Nội",
                "id": "here:cm:namedplace:123",
                "resultType": "locality",
                "address": {
                    "label": "Hà Nội, Việt Nam",
                    "countryCode": "VNM",
                    "city": "Hà Nội",
                },
            }
        ]
    )

    result = asyncio.run(
        resolver.resolve(
            _candidate("Hà Nội"),
            destination="Hà Nội",
        )
    )

    assert result.status == "unresolved"
    assert result.resolution_reason is not None
    assert "not_a_place" in result.resolution_reason
    assert "coordinates_missing" in result.resolution_reason


def test_here_resolver_matches_bilingual_provider_title() -> None:
    resolver = FakeHereResolver(
        [
            {
                "title": (
                    "Da Nang Museum Of Cham Sculpture "
                    "(Bảo Tàng Điêu Khắc Chăm Đà Nẵng)"
                ),
                "id": "here:pds:place:704jx7ps-456",
                "resultType": "place",
                "address": {
                    "label": "Quận Hải Châu, Đà Nẵng, Việt Nam",
                    "countryCode": "VNM",
                    "countryName": "Việt Nam",
                    "city": "Đà Nẵng",
                },
                "position": {"lat": 16.0605, "lng": 108.2235},
            }
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Bảo tàng Điêu khắc Chăm Đà Nẵng",
        searchNames=["Da Nang Museum of Cham Sculpture"],
        category="culture",
        sources=[],
        confidence=1.0,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Đà Nẵng")
    )

    assert result.status == "resolved"
    assert result.resolution_reason is None


def test_here_resolve_many_caps_concurrency_and_preserves_order() -> None:
    resolver = ConcurrencyTrackingHereResolver()
    candidates = [_candidate(f"Địa điểm {index}") for index in range(8)]

    results = asyncio.run(
        resolver.resolve_many(candidates, destination="Hà Nội")
    )

    assert resolver.max_active == 4
    assert [result.candidate.name for result in results] == [
        candidate.name for candidate in candidates
    ]


def test_here_rate_limiter_does_not_hold_lock_during_network_wait(
    monkeypatch: Any,
) -> None:
    active = 0
    max_active = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, list[Any]]:
            return {"items": []}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            params: dict[str, str | int],
        ) -> FakeResponse:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1
            return FakeResponse()

    monkeypatch.setattr(
        resolver_module.httpx,
        "AsyncClient",
        FakeAsyncClient,
    )
    resolver = HerePlaceResolver(
        base_url="https://example.invalid",
        api_key="test-key",
    )
    resolver.min_interval_seconds = 0.0

    async def request_twice() -> None:
        await asyncio.gather(
            resolver._request_json(
                "https://example.invalid/one",
                params={"q": "one"},
            ),
            resolver._request_json(
                "https://example.invalid/two",
                params={"q": "two"},
            ),
        )

    asyncio.run(request_twice())

    assert max_active == 2


def test_fallback_resolver_uses_nominatim_after_here_miss() -> None:
    candidate = _candidate()
    here_result = PlaceResolution(
        candidate=candidate,
        status="unresolved",
        resolutionReason="not_found",
        provider="here",
        name=candidate.name,
    )
    nominatim_result = PlaceResolution(
        candidate=candidate,
        status="resolved",
        provider="nominatim",
        externalId="node:123",
        name=candidate.name,
        latitude="16.0592",
        longitude="108.2131",
    )
    primary = StaticPlaceResolver(here_result)
    fallback = StaticPlaceResolver(nominatim_result)
    resolver = FallbackPlaceResolver(primary, fallback)

    result = asyncio.run(
        resolver.resolve(candidate, destination="Đà Nẵng")
    )

    assert primary.calls == 1
    assert fallback.calls == 1
    assert result.status == "resolved"
    assert result.provider == "nominatim"


def test_fallback_resolver_skips_nominatim_for_usable_here_result() -> None:
    candidate = _candidate()
    here_result = PlaceResolution(
        candidate=candidate,
        status="resolved",
        provider="here",
        externalId="here:pds:place:123",
        name=candidate.name,
        latitude="16.0592",
        longitude="108.2131",
    )
    fallback_result = PlaceResolution(
        candidate=candidate,
        status="unresolved",
        resolutionReason="not_found",
        provider="nominatim",
        name=candidate.name,
    )
    primary = StaticPlaceResolver(here_result)
    fallback = StaticPlaceResolver(fallback_result)
    resolver = FallbackPlaceResolver(primary, fallback)

    result = asyncio.run(
        resolver.resolve(candidate, destination="Đà Nẵng")
    )

    assert primary.calls == 1
    assert fallback.calls == 0
    assert result.provider == "here"


def test_fallback_resolve_many_only_sends_here_misses_to_sequential_nominatim(
) -> None:
    candidates = [_candidate(f"Địa điểm {index}") for index in range(8)]
    unresolved_names = {
        candidates[1].name,
        candidates[4].name,
        candidates[6].name,
    }
    primary = ConcurrencyTrackingHereResolver(
        unresolved_names=unresolved_names,
    )
    fallback = ConcurrencyTrackingNominatimResolver()
    resolver = FallbackPlaceResolver(primary, fallback)

    results = asyncio.run(
        resolver.resolve_many(candidates, destination="Hà Nội")
    )

    assert primary.max_active == 4
    assert fallback.max_active == 1
    assert fallback.names == [
        candidates[1].name,
        candidates[4].name,
        candidates[6].name,
    ]
    assert [result.candidate.name for result in results] == [
        candidate.name for candidate in candidates
    ]
    assert [result.provider for result in results] == [
        "here",
        "nominatim",
        "here",
        "here",
        "nominatim",
        "here",
        "nominatim",
        "here",
    ]


def test_runtime_wires_here_primary_with_nominatim_fallback(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "here",
    )
    monkeypatch.setattr(
        dependencies.settings,
        "here_api_key",
        "test-key",
    )

    resolver = dependencies._get_place_resolver()

    assert isinstance(resolver, FallbackPlaceResolver)
    assert isinstance(resolver.primary, HerePlaceResolver)
    assert isinstance(resolver.fallback, NominatimPlaceResolver)
    assert resolver.primary.max_concurrency == 4


def test_runtime_uses_nominatim_when_here_key_is_missing(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "here",
    )
    monkeypatch.setattr(dependencies.settings, "here_api_key", None)

    resolver = dependencies._get_place_resolver()

    assert isinstance(resolver, NominatimPlaceResolver)


def test_nominatim_resolver_maps_provider_result_to_place_contract() -> None:
    resolver = FakeNominatimResolver(
        [
            {
                "osm_type": "node",
                "osm_id": 123,
                "name": "Mì Quảng Bà Mua",
                "display_name": "Mì Quảng Bà Mua, Đà Nẵng, Việt Nam",
                "lat": "16.0592",
                "lon": "108.2131",
                "importance": 0.5,
                "address": {
                    "city": "Đà Nẵng",
                    "country": "Việt Nam",
                    "country_code": "vn",
                },
                "extratags": {
                    "description": "Nhà hàng chuyên món mì Quảng."
                },
                "licence": "Data © OpenStreetMap contributors",
            }
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Mì Quảng Bà Mua",
        category="food",
        sources=[{"type": "url", "url": "https://example.com/reel"}],
        confidence=0.8,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Đà Nẵng")
    )

    assert result.status == "resolved"
    assert result.external_id == "node:123"
    assert result.country_code == "VN"
    assert str(result.latitude) == "16.0592"
    assert result.data_confidence == "high"


def test_nominatim_resolver_keeps_unmatched_candidate_without_question() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Quán chưa xác định",
        category="food",
        sources=[{"type": "ocr", "url": None}],
        confidence=0.4,
    )

    result = asyncio.run(
        FakeNominatimResolver([]).resolve(
            candidate,
            destination="Đà Nẵng",
        )
    )

    assert result.status == "unresolved"
    assert result.name == "Quán chưa xác định"
    assert result.latitude is None


def test_nominatim_resolver_prefers_vietnamese_name_and_best_matching_result() -> None:
    resolver = FakeNominatimResolver(
        [
            {
                "name": "Hà Nội",
                "display_name": "Hà Nội, Việt Nam",
                "lat": "21.0285",
                "lon": "105.8542",
                "importance": 0.9,
                "address": {
                    "city": "Hà Nội",
                    "country": "Việt Nam",
                    "country_code": "vn",
                },
                "namedetails": {"name": "Hà Nội", "name:en": "Hanoi"},
            },
            {
                "osm_type": "way",
                "osm_id": 456,
                "name": "Bảo tàng Dân tộc học Việt Nam",
                "display_name": (
                    "Bảo tàng Dân tộc học Việt Nam, đường Nguyễn Văn Huyên, "
                    "Cầu Giấy, Hà Nội, Việt Nam"
                ),
                "lat": "21.0403",
                "lon": "105.7980",
                "importance": 0.4,
                "address": {
                    "city": "Hà Nội",
                    "suburb": "Cầu Giấy",
                    "country": "Việt Nam",
                    "country_code": "vn",
                },
                "namedetails": {
                    "name": "Bảo tàng Dân tộc học Việt Nam",
                    "name:vi": "Bảo tàng Dân tộc học Việt Nam",
                    "name:en": "Vietnam Museum of Ethnology",
                },
            },
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Vietnam Museum of Ethnology",
        category="culture",
        sources=[{"type": "url", "url": "https://example.com/tiktok"}],
        confidence=0.9,
    )

    result = asyncio.run(resolver.resolve(candidate, destination="Hà Nội"))

    assert result.status == "resolved"
    assert result.name == "Bảo tàng Dân tộc học Việt Nam"
    assert result.address is not None
    assert "Nguyễn Văn Huyên" in result.address
    assert str(result.latitude) == "21.0403"
    assert str(result.longitude) == "105.7980"


def test_nominatim_rejects_hang_mua_phone_shop_false_match() -> None:
    resolver = FakeNominatimResolver(
        [
            {
                "osm_type": "node",
                "osm_id": 999,
                "name": (
                    "Cửa Hàng Mua Bán Sửa Chữa Chuyên Nghiệp "
                    "ĐTDĐ Nokia"
                ),
                "display_name": (
                    "Cửa Hàng Mua Bán Sửa Chữa Chuyên Nghiệp "
                    "ĐTDĐ Nokia, Hà Nội, Việt Nam"
                ),
                "lat": "21.0747",
                "lon": "105.7731",
                "class": "shop",
                "type": "mobile_phone",
                "address": {
                    "city": "Hà Nội",
                    "country": "Việt Nam",
                },
            }
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Hang Múa",
        category="nature",
        searchRegion="Ninh Bình",
        sources=[{"type": "url", "url": "https://example.com/reel"}],
        confidence=0.9,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert resolver.queries == ["Hang Múa, Ninh Bình"]
    assert result.status == "unresolved"
    assert result.resolution_reason is not None
    assert "region_mismatch" in result.resolution_reason
    assert "category_mismatch" in result.resolution_reason


def test_nominatim_resolves_day_trip_place_in_search_region() -> None:
    resolver = FakeNominatimResolver(
        [
            {
                "osm_type": "node",
                "osm_id": 1000,
                "name": "Hang Múa",
                "display_name": (
                    "Hang Múa, Hoa Lư, Ninh Bình, Việt Nam"
                ),
                "lat": "20.2298",
                "lon": "105.9367",
                "class": "tourism",
                "type": "attraction",
                "address": {
                    "city": "Hoa Lư",
                    "state": "Ninh Bình",
                    "country": "Việt Nam",
                },
            }
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Hang Múa",
        category="nature",
        searchRegion="Ninh Bình",
        sources=[{"type": "url", "url": "https://example.com/reel"}],
        confidence=0.9,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert result.status == "resolved"
    assert result.resolution_reason is None
    assert result.city == "Hoa Lư"
    assert str(result.latitude) == "20.2298"
