import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.modules.places.resolver import (
    DatabasePlaceResolver,
    FallbackPlaceResolver,
    GoogleMapsScraperPlaceResolver,
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


class FakePlaceRepository:
    def __init__(self, places: list[Any]) -> None:
        self.places = places
        self.region_keys: list[str | None] = []

    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Any]:
        self.region_keys.append(region_key)
        return self.places[:limit]


class FakeGoogleMapsScraperResolver(GoogleMapsScraperPlaceResolver):
    def __init__(self, results_by_query: dict[str, list[dict[str, Any]]]) -> None:
        super().__init__(
            executable="google-maps-scraper-test",
        )
        self.results_by_query = results_by_query
        self.queries: list[str] = []

    async def _search(
        self,
        queries: list[str],
    ) -> list[dict[str, Any]]:
        self.queries.extend(queries)
        return [
            result
            for query in queries
            for result in self.results_by_query.get(query, [])
        ]


class RecordingFallbackResolver(PlaceResolver):
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


def test_runtime_wires_nominatim_when_scraper_is_disabled(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "nominatim",
    )
    monkeypatch.setattr(
        dependencies.settings,
        "google_maps_scraper_executable",
        None,
    )
    monkeypatch.setattr(
        dependencies.settings,
        "google_maps_scraper_work_dir",
        None,
    )

    resolver = dependencies._get_place_resolver()

    assert isinstance(resolver, NominatimPlaceResolver)


def test_runtime_wires_database_before_nominatim(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "nominatim",
    )
    monkeypatch.setattr(
        dependencies.settings,
        "google_maps_scraper_executable",
        None,
    )
    monkeypatch.setattr(
        dependencies.settings,
        "google_maps_scraper_work_dir",
        None,
    )
    repository = FakePlaceRepository([])

    resolver = dependencies._get_place_resolver(repository)  # type: ignore[arg-type]

    assert isinstance(resolver, FallbackPlaceResolver)
    assert isinstance(resolver.primary, DatabasePlaceResolver)
    assert isinstance(resolver.fallback, NominatimPlaceResolver)


def test_runtime_wires_google_maps_scraper_after_database_and_nominatim(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "nominatim",
    )
    monkeypatch.setattr(
        dependencies.settings,
        "google_maps_scraper_executable",
        "/usr/local/bin/google-maps-scraper",
    )
    monkeypatch.setattr(
        dependencies.settings,
        "google_maps_scraper_work_dir",
        None,
    )

    resolver = dependencies._get_place_resolver(FakePlaceRepository([]))  # type: ignore[arg-type]

    assert isinstance(resolver, FallbackPlaceResolver)
    assert isinstance(resolver.primary, DatabasePlaceResolver)
    assert isinstance(resolver.fallback, FallbackPlaceResolver)
    assert isinstance(resolver.fallback.primary, NominatimPlaceResolver)
    assert isinstance(
        resolver.fallback.fallback,
        GoogleMapsScraperPlaceResolver,
    )


def test_google_maps_scraper_resolves_coordinates_with_alias_name() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Ethnology Museum",
        searchNames=["Bảo tàng Dân tộc học Việt Nam"],
        category="culture",
        searchRegion="Hà Nội",
    )
    alias_query = "Bảo tàng Dân tộc học Việt Nam, Hà Nội"
    resolver = FakeGoogleMapsScraperResolver(
        {
            alias_query: [
                {
                    "title": "Bảo tàng Dân tộc học Việt Nam",
                    "category": "Museum",
                    "address": "Nguyễn Văn Huyên, Cầu Giấy, Hà Nội",
                    "latitude": 21.0403,
                    # Upstream preserves this legacy misspelling.
                    "longtitude": 105.7980,
                    "place_id": "ChIJ-test",
                    "complete_address": {
                        "city": "Hà Nội",
                        "country": "Việt Nam",
                        "country_code": "VN",
                    },
                }
            ]
        }
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert resolver.queries == [
        "Ethnology Museum, Hà Nội",
        alias_query,
    ]
    assert result.status == "resolved"
    assert result.provider == "google_maps_scraper"
    assert result.external_id == "ChIJ-test"
    assert str(result.latitude) == "21.0403"
    assert str(result.longitude) == "105.798"
    assert result.attribution == (
        "Google Maps data via gosom/google-maps-scraper"
    )


def test_google_maps_scraper_fills_coordinates_missing_from_places_db() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Hidden Garden",
        searchNames=["Vườn Ẩn"],
        category="attraction",
        searchRegion="Hà Nội",
    )
    repository = FakePlaceRepository(
        [
            SimpleNamespace(
                id="place-hidden-garden",
                name="Hidden Garden",
                place_type="attraction",
                address="Hà Nội",
                city="Hà Nội",
                country="Việt Nam",
                country_code="VN",
                primary_area=None,
                latitude=None,
                longitude=None,
                data_confidence="medium",
                source_fetched_at=None,
                metadata_json={"aliases": ["Vườn Ẩn"]},
            )
        ]
    )
    scraper = FakeGoogleMapsScraperResolver(
        {
            "Hidden Garden, Hà Nội": [
                {
                    "title": "Hidden Garden",
                    "category": "Tourist attraction",
                    "address": "Tây Hồ, Hà Nội",
                    "latitude": 21.070,
                    "longitude": 105.820,
                }
            ]
        }
    )
    resolver = FallbackPlaceResolver(
        DatabasePlaceResolver(repository),
        scraper,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert result.status == "resolved"
    assert result.provider == "google_maps_scraper"
    assert str(result.latitude) == "21.07"
    assert str(result.longitude) == "105.82"
    assert scraper.queries == [
        "Hidden Garden, Hà Nội",
        "Vườn Ẩn, Hà Nội",
    ]


def test_google_maps_scraper_rejects_wrong_region() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Common Cafe",
        category="cafe",
        searchRegion="Hà Nội",
    )
    resolver = FakeGoogleMapsScraperResolver(
        {
            "Common Cafe, Hà Nội": [
                {
                    "title": "Common Cafe",
                    "category": "Cafe",
                    "address": "District 1, Ho Chi Minh City",
                    "latitude": 10.776,
                    "longitude": 106.700,
                }
            ]
        }
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert result.status == "unresolved"
    assert result.resolution_reason == "region_mismatch"


def test_google_maps_scraper_runs_cli_without_api_key(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "fake-google-maps-scraper"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

assert "-input" in sys.argv
assert "-results" in sys.argv
assert not any("api-key" in value for value in sys.argv)
results_path = pathlib.Path(sys.argv[sys.argv.index("-results") + 1])
results_path.write_text(json.dumps([{
    "title": "CLI Place",
    "category": "Tourist attraction",
    "address": "Hoàn Kiếm, Hà Nội",
    "latitude": 21.028,
    "longitude": 105.852,
    "place_id": "cli-place-id"
}]), encoding="utf-8")
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    resolver = GoogleMapsScraperPlaceResolver(
        executable=str(executable),
        timeout_seconds=5,
    )
    candidate = UnifiedPlaceCandidate(
        name="CLI Place",
        category="attraction",
        searchRegion="Hà Nội",
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert result.status == "resolved"
    assert result.provider == "google_maps_scraper"
    assert result.external_id == "cli-place-id"
    assert str(result.latitude) == "21.028"
    assert str(result.longitude) == "105.852"


def test_google_maps_scraper_uses_shared_worker_without_api_key(
    tmp_path: Path,
) -> None:
    resolver = GoogleMapsScraperPlaceResolver(
        work_dir=tmp_path,
        timeout_seconds=5,
    )
    candidate = UnifiedPlaceCandidate(
        name="Worker Place",
        category="attraction",
        searchRegion="Hà Nội",
    )

    async def run_scenario() -> PlaceResolution:
        resolve_task = asyncio.create_task(
            resolver.resolve(candidate, destination="Hà Nội")
        )
        requests_dir = tmp_path / "requests"
        request_paths: list[Path] = []
        for _ in range(50):
            request_paths = list(requests_dir.glob("*.txt"))
            if request_paths:
                break
            await asyncio.sleep(0.02)
        assert len(request_paths) == 1
        request_id = request_paths[0].stem
        responses_dir = tmp_path / "responses"
        responses_dir.mkdir(parents=True, exist_ok=True)
        (responses_dir / f"{request_id}.json").write_text(
            json.dumps(
                [
                    {
                        "title": "Worker Place",
                        "category": "Tourist attraction",
                        "address": "Hoàn Kiếm, Hà Nội",
                        "latitude": 21.028,
                        "longitude": 105.852,
                        "place_id": "worker-place-id",
                    }
                ]
            ),
            encoding="utf-8",
        )
        return await resolve_task

    result = asyncio.run(run_scenario())

    assert result.status == "resolved"
    assert result.provider == "google_maps_scraper"
    assert result.external_id == "worker-place-id"


def test_database_resolver_matches_bilingual_alias_before_provider() -> None:
    repository = FakePlaceRepository(
        [
            SimpleNamespace(
                id="place-ethnology",
                name="Bảo tàng Dân tộc học Việt Nam",
                place_type="culture",
                address="Nguyễn Văn Huyên, Cầu Giấy, Hà Nội",
                city="Hà Nội",
                country="Việt Nam",
                country_code="VN",
                primary_area="Cầu Giấy",
                latitude=Decimal("21.0403"),
                longitude=Decimal("105.7980"),
                data_confidence="high",
                source_fetched_at=datetime.now(timezone.utc),
                metadata_json={
                    "aliases": [
                        "Vietnam Museum of Ethnology",
                        "Ethnology Museum",
                    ],
                    "attribution": "OpenStreetMap contributors",
                },
            )
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Ethnology Museum",
        searchNames=["Bảo tàng Dân tộc học Việt Nam"],
        category="culture",
        searchRegion="Hanoi",
    )

    result = asyncio.run(
        DatabasePlaceResolver(repository).resolve(
            candidate,
            destination="Hanoi",
        )
    )

    assert repository.region_keys == ["vn,ha-noi"]
    assert result.status == "resolved"
    assert result.provider == "database"
    assert result.external_id == "place-ethnology"
    assert result.name == "Bảo tàng Dân tộc học Việt Nam"


def test_database_resolver_finds_english_place_from_vietnamese_source() -> None:
    repository = FakePlaceRepository(
        [
            SimpleNamespace(
                id="place-english-catalog",
                name="Vietnam Museum of Ethnology",
                place_type="culture",
                address="Nguyen Van Huyen, Hanoi",
                city="Hanoi",
                country="Vietnam",
                country_code="vn",
                primary_area="Cau Giay",
                latitude=Decimal("21.0403"),
                longitude=Decimal("105.7980"),
                data_confidence="high",
                source_fetched_at=datetime.now(timezone.utc),
                metadata_json={},
            )
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Bảo tàng Dân tộc học Việt Nam",
        originalName="Bảo tàng Dân tộc học Việt Nam",
        englishNames=["Vietnam Museum of Ethnology"],
        vietnameseNames=["Bảo tàng Dân tộc học Việt Nam"],
        searchNames=[
            "Vietnam Museum of Ethnology",
            "Bảo tàng Dân tộc học Việt Nam",
        ],
        category="culture",
        searchRegion="Hà Nội",
    )

    result = asyncio.run(
        DatabasePlaceResolver(repository).resolve(
            candidate,
            destination="Hà Nội",
        )
    )

    assert result.status == "resolved"
    assert result.provider == "database"
    assert result.external_id == "place-english-catalog"
    assert result.country_code == "VN"
    assert str(result.latitude) == "21.0403"
    assert str(result.longitude) == "105.7980"


def test_fallback_chain_skips_nominatim_when_database_matches() -> None:
    candidate = UnifiedPlaceCandidate(name="Phố Đồng Xuân")
    database_result = PlaceResolution(
        candidate=candidate,
        status="resolved",
        provider="database",
        externalId="place-dong-xuan",
        name="Phố Đồng Xuân",
        latitude=Decimal("21.0381"),
        longitude=Decimal("105.8490"),
        dataConfidence="high",
    )
    database = RecordingFallbackResolver(database_result)
    nominatim = RecordingFallbackResolver(
        PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="nominatim",
            name="Phố Đồng Xuân",
            latitude=Decimal("21.0381"),
            longitude=Decimal("105.8490"),
        )
    )
    resolver = FallbackPlaceResolver(database, nominatim)

    result = asyncio.run(resolver.resolve(candidate, destination="Hà Nội"))

    assert result.provider == "database"
    assert database.calls == 1
    assert nominatim.calls == 0


def test_fallback_chain_calls_nominatim_after_database_miss() -> None:
    candidate = UnifiedPlaceCandidate(name="Train Street Southern Entrance")
    database = RecordingFallbackResolver(
        PlaceResolution(
            candidate=candidate,
            status="unresolved",
            resolutionReason="not_found",
            provider="database",
            name=candidate.name,
        )
    )
    nominatim = RecordingFallbackResolver(
        PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="nominatim",
            externalId="node:123",
            name="Hanoi Train Street",
            latitude=Decimal("21.0180"),
            longitude=Decimal("105.8410"),
        )
    )
    resolver = FallbackPlaceResolver(database, nominatim)

    result = asyncio.run(resolver.resolve(candidate, destination="Hà Nội"))

    assert result.provider == "nominatim"
    assert database.calls == 1
    assert nominatim.calls == 1


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
