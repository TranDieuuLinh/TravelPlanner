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
    PlaceResolution,
    PlaceResolver,
)
from app.modules.plans import dependencies
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


class FakePlaceRepository:
    def __init__(self, places: list[Any]) -> None:
        self.places = places
        self.region_keys: list[str | None] = []
        self.global_name_searches: list[list[str]] = []

    def list_active_for_planner_research(
        self,
        region_key: str | None = None,
        *,
        limit: int = 5000,
    ) -> list[Any]:
        self.region_keys.append(region_key)
        return self.places[:limit]

    def search_active_by_names(
        self,
        names: list[str],
        *,
        limit: int = 100,
    ) -> list[Any]:
        self.global_name_searches.append(names)
        keys = {" ".join(name.split()).casefold() for name in names}
        return [
            place
            for place in self.places
            if any(
                key in " ".join(place.name.split()).casefold()
                for key in keys
            )
        ][:limit]


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


def test_runtime_uses_provisional_resolver_when_scraper_is_disabled(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "google_maps_scraper",
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

    assert isinstance(resolver, dependencies.ProvisionalPlaceResolver)


def test_runtime_wires_database_before_provisional_when_scraper_is_disabled(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "google_maps_scraper",
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
    assert isinstance(resolver.fallback, dependencies.ProvisionalPlaceResolver)


def test_runtime_wires_database_before_google_maps_scraper(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        dependencies.settings,
        "place_resolver_provider",
        "google_maps_scraper",
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
    assert isinstance(resolver.fallback, GoogleMapsScraperPlaceResolver)


def test_google_maps_scraper_resolves_coordinates_with_alias_name() -> None:
    candidate = UnifiedPlaceCandidate(
        name="Ethnology Museum",
        vietnameseNames=["Bảo tàng Dân tộc học Việt Nam"],
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

    assert resolver.queries == [alias_query]
    assert result.status == "resolved"
    assert result.provider == "google_maps_scraper"
    assert result.name == "Bảo tàng Dân tộc học Việt Nam"
    assert result.external_id == "ChIJ-test"
    assert str(result.latitude) == "21.0403"
    assert str(result.longitude) == "105.798"
    assert result.attribution == (
        "Google Maps data via gosom/google-maps-scraper"
    )
    assert result.provider_attempts[0].alias_query_count == 1
    assert result.provider_attempts[0].outcome == "resolved"


def test_google_maps_scraper_defaults_to_one_synchronous_alias_query() -> None:
    candidate = UnifiedPlaceCandidate(
        name="English Place",
        vietnameseNames=["Địa điểm tiếng Việt"],
        searchRegion="Hà Nội",
    )
    resolver = FakeGoogleMapsScraperResolver(
        {
            "Địa điểm tiếng Việt, Hà Nội": [],
            "English Place, Hà Nội": [
                {
                    "title": "English Place",
                    "address": "Hà Nội",
                    "latitude": 21.0,
                    "longitude": 105.8,
                }
            ],
        }
    )

    result = asyncio.run(resolver.resolve(candidate, destination="Hà Nội"))

    assert resolver.queries == ["Địa điểm tiếng Việt, Hà Nội"]
    assert result.status == "unresolved"
    assert result.provider_attempts[0].alias_query_count == 1


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
    assert scraper.queries == ["Hidden Garden, Hà Nội"]
    assert [attempt.provider for attempt in result.provider_attempts] == [
        "database",
        "google_maps_scraper",
    ]
    assert [attempt.outcome for attempt in result.provider_attempts] == [
        "unresolved",
        "resolved",
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


def test_google_maps_scraper_uses_evidenced_nearby_place_context() -> None:
    contextual_query = "Coffee 74, Hanoi train street, Hanoi"
    candidate = UnifiedPlaceCandidate(
        name="Coffee 74",
        category="cafe",
        searchRegion="Hanoi",
        sourceEvidence={
            "ocr": "Coffee 74 beer storefront along the Hanoi train street",
        },
        sourceActivity=(
            "watching trains pass by while having drinks at Coffee 74"
        ),
    )
    resolver = FakeGoogleMapsScraperResolver(
        {
            contextual_query: [
                {
                    "title": "Coffee 74",
                    "category": "Cafe",
                    "address": "5 Trần Phú, Hoàn Kiếm, Hà Nội",
                    "latitude": 21.0295,
                    "longitude": 105.8430,
                    "place_id": "coffee-74-tran-phu",
                }
            ]
        }
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hanoi")
    )

    assert resolver.queries == [contextual_query]
    assert result.status == "resolved"
    assert result.external_id == "coffee-74-tran-phu"
    assert result.address == "5 Trần Phú, Hoàn Kiếm, Hà Nội"


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
    "place_id": "cli-place-id",
    "review_rating": 4.7,
    "review_count": 1284,
    "plus_code": "2VJ2+P2 Hoàn Kiếm, Hà Nội",
    "website": "https://example.com/place",
    "phone": "+84 24 1234 5678",
    "descriptions": ["Điểm tham quan lịch sử."],
    "opening_hours": [{
        "dayOfWeek": 1,
        "dayName": "Thứ Hai",
        "rawTimeSlots": "08:00–17:00",
        "is24Hours": False,
        "sourceFormat": "google_maps"
    }]
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
    assert str(result.rating) == "4.7"
    assert result.review_count == 1284
    assert result.plus_code == "2VJ2+P2 Hoàn Kiếm, Hà Nội"
    assert result.description == "Điểm tham quan lịch sử."
    assert result.opening_hours[0]["dayOfWeek"] == 1
    assert result.place_metadata == {
        "category": "Tourist attraction",
        "website": "https://example.com/place",
        "phone": "+84 24 1234 5678",
    }


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
            request_paths = list(requests_dir.glob("*.json"))
            if request_paths:
                break
            await asyncio.sleep(0.02)
        assert len(request_paths) == 1
        request_id = request_paths[0].stem
        request = json.loads(request_paths[0].read_text(encoding="utf-8"))
        assert request["queries"] == ["Worker Place, Hà Nội"]
        assert request["deadlineAtMs"] > request["createdAtMs"]
        responses_dir = tmp_path / "responses"
        responses_dir.mkdir(parents=True, exist_ok=True)
        (responses_dir / f"{request_id}.json").write_text(
            json.dumps(
                {
                    "results": [
                    {
                        "title": "Worker Place",
                        "category": "Tourist attraction",
                        "address": "Hoàn Kiếm, Hà Nội",
                        "latitude": 21.028,
                        "longitude": 105.852,
                        "place_id": "worker-place-id",
                    }
                    ],
                    "telemetry": {
                        "queueWaitSeconds": 0.125,
                        "executionSeconds": 0.75,
                    },
                }
            ),
            encoding="utf-8",
        )
        return await resolve_task

    result = asyncio.run(run_scenario())

    assert result.status == "resolved"
    assert result.provider == "google_maps_scraper"
    assert result.external_id == "worker-place-id"
    assert result.provider_attempts[0].queue_wait_seconds == 0.125
    assert result.provider_attempts[0].execution_seconds == 0.75


def test_google_maps_worker_timeout_emits_cancellation_and_attempt_timing(
    tmp_path: Path,
) -> None:
    resolver = GoogleMapsScraperPlaceResolver(
        work_dir=tmp_path,
        timeout_seconds=0.08,
    )
    candidate = UnifiedPlaceCandidate(name="Slow Place", searchRegion="Hà Nội")

    async def run_scenario() -> PlaceResolution:
        task = asyncio.create_task(
            resolver.resolve(candidate, destination="Hà Nội")
        )
        request_path: Path | None = None
        for _ in range(20):
            paths = list((tmp_path / "requests").glob("*.json"))
            if paths:
                request_path = paths[0]
                break
            await asyncio.sleep(0.01)
        assert request_path is not None
        request = json.loads(request_path.read_text(encoding="utf-8"))
        status_dir = tmp_path / "status"
        status_dir.mkdir(parents=True, exist_ok=True)
        (status_dir / request_path.name).write_text(
            json.dumps(
                {
                    "startedAtMs": request["createdAtMs"] + 20,
                }
            ),
            encoding="utf-8",
        )
        return await task

    result = asyncio.run(run_scenario())

    cancellations = list((tmp_path / "cancellations").glob("*.cancel"))
    assert len(cancellations) == 1
    assert result.status == "unresolved"
    assert result.resolution_reason == "timeout"
    assert result.provider_attempts[0].outcome == "timeout"
    assert result.provider_attempts[0].queue_wait_seconds == 0.02
    assert result.provider_attempts[0].execution_seconds > 0


def test_google_maps_scraper_resolves_many_with_bounded_concurrency() -> None:
    class TrackingResolver(GoogleMapsScraperPlaceResolver):
        def __init__(self) -> None:
            super().__init__(
                executable="google-maps-scraper-test",
                max_concurrency=2,
            )
            self.active = 0
            self.maximum_active = 0

        async def resolve(
            self,
            candidate: UnifiedPlaceCandidate,
            *,
            destination: str,
        ) -> PlaceResolution:
            self.active += 1
            self.maximum_active = max(self.maximum_active, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return PlaceResolution(
                candidate=candidate,
                status="unresolved",
                name=candidate.name,
                city=destination,
            )

    resolver = TrackingResolver()
    candidates = [
        UnifiedPlaceCandidate(name=f"Place {index}")
        for index in range(4)
    ]

    results = asyncio.run(
        resolver.resolve_many(candidates, destination="Hà Nội")
    )

    assert resolver.maximum_active == 2
    assert [result.name for result in results] == [
        "Place 0",
        "Place 1",
        "Place 2",
        "Place 3",
    ]


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


def test_database_resolver_falls_back_to_global_name_when_region_misses() -> None:
    class RegionMissRepository(FakePlaceRepository):
        def list_active_for_planner_research(
            self,
            region_key: str | None = None,
            *,
            limit: int = 5000,
        ) -> list[Any]:
            self.region_keys.append(region_key)
            return []

    repository = RegionMissRepository(
        [
            SimpleNamespace(
                id="place-hidden-garden-hanoi",
                name="Hidden Garden",
                place_type="cafe",
                address="Tây Hồ, Hà Nội",
                city="Hà Nội",
                country="Việt Nam",
                country_code="VN",
                primary_area="Tây Hồ",
                latitude=Decimal("21.0700"),
                longitude=Decimal("105.8200"),
                data_confidence="high",
                source_fetched_at=datetime.now(timezone.utc),
                metadata_json={},
                region_key="vn,ha-noi,tay-ho",
                status="active",
            )
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Hidden Garden",
        category="cafe",
        searchRegion="Tây Hồ",
    )

    result = asyncio.run(
        DatabasePlaceResolver(repository).resolve(
            candidate,
            destination="Hà Nội",
        )
    )

    assert repository.region_keys == ["vn,tay-ho"]
    assert repository.global_name_searches == [["Hidden Garden"]]
    assert result.status == "resolved"
    assert result.provider == "database"
    assert result.external_id == "place-hidden-garden-hanoi"


def test_database_resolver_does_not_guess_between_global_duplicate_names() -> None:
    class RegionMissRepository(FakePlaceRepository):
        def list_active_for_planner_research(
            self,
            region_key: str | None = None,
            *,
            limit: int = 5000,
        ) -> list[Any]:
            self.region_keys.append(region_key)
            return []

    def duplicate(place_id: str, city: str, region_key: str) -> Any:
        return SimpleNamespace(
            id=place_id,
            name="Common Cafe",
            place_type="cafe",
            address=city,
            city=city,
            country="Việt Nam",
            country_code="VN",
            primary_area=None,
            latitude=Decimal("21.0000"),
            longitude=Decimal("105.0000"),
            data_confidence="high",
            source_fetched_at=datetime.now(timezone.utc),
            metadata_json={},
            region_key=region_key,
            status="active",
        )

    repository = RegionMissRepository(
        [
            duplicate("common-cafe-da-lat", "Đà Lạt", "vn,da-lat"),
            duplicate("common-cafe-da-nang", "Đà Nẵng", "vn,da-nang"),
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Common Cafe",
        category="cafe",
        searchRegion="Hà Nội",
    )

    result = asyncio.run(
        DatabasePlaceResolver(repository).resolve(
            candidate,
            destination="Hà Nội",
        )
    )

    assert result.status == "unresolved"
    assert result.resolution_reason == "ambiguous_name"


def test_database_resolver_uses_source_address_to_choose_branch() -> None:
    def branch(place_id: str, name: str, address: str) -> Any:
        return SimpleNamespace(
            id=place_id,
            name=name,
            place_type="cafe",
            address=address,
            city="Hà Nội",
            country="Việt Nam",
            country_code="VN",
            primary_area=address,
            latitude=Decimal("21.0300"),
            longitude=Decimal("105.8500"),
            data_confidence="high",
            source_fetched_at=datetime.now(timezone.utc),
            metadata_json={},
            region_key="vn,ha-noi",
            status="active",
        )

    repository = FakePlaceRepository(
        [
            branch(
                "highlands-ham-ca-map",
                "Highlands Coffee Hàm Cá Mập",
                "Hàm Cá Mập, Hoàn Kiếm, Hà Nội",
            ),
            branch(
                "highlands-tay-ho",
                "Highlands Coffee Tây Hồ",
                "Tây Hồ, Hà Nội",
            ),
        ]
    )
    candidate = UnifiedPlaceCandidate(
        name="Highlands Coffee",
        category="cafe",
        searchRegion="Hà Nội",
        addressHint="Hàm Cá Mập, Hoàn Kiếm",
    )

    result = asyncio.run(
        DatabasePlaceResolver(repository).resolve(
            candidate,
            destination="Hà Nội",
        )
    )

    assert result.status == "resolved"
    assert result.external_id == "highlands-ham-ca-map"
    assert result.resolution_reason == "matched_source_location"


def test_database_resolver_uses_route_context_to_choose_clear_branch() -> None:
    def place(
        place_id: str,
        name: str,
        latitude: str,
        longitude: str,
    ) -> Any:
        return SimpleNamespace(
            id=place_id,
            name=name,
            place_type="attraction" if "Highlands" not in name else "cafe",
            address="Hoàn Kiếm, Hà Nội",
            city="Hà Nội",
            country="Việt Nam",
            country_code="VN",
            primary_area="Hoàn Kiếm",
            latitude=Decimal(latitude),
            longitude=Decimal(longitude),
            data_confidence="high",
            source_fetched_at=datetime.now(timezone.utc),
            metadata_json={},
            region_key="vn,ha-noi",
            status="active",
        )

    repository = FakePlaceRepository(
        [
            place("ho-guom", "Hồ Hoàn Kiếm", "21.0280", "105.8520"),
            place(
                "highlands-near-route",
                "Highlands Coffee Hàm Cá Mập",
                "21.0290",
                "105.8530",
            ),
            place(
                "highlands-far-route",
                "Highlands Coffee Tây Hồ",
                "21.0800",
                "105.8200",
            ),
            place(
                "nha-tho-lon",
                "Nhà thờ Lớn Hà Nội",
                "21.0300",
                "105.8550",
            ),
        ]
    )
    candidates = [
        UnifiedPlaceCandidate(
            name="Hồ Hoàn Kiếm",
            category="attraction",
            searchRegion="Hà Nội",
            sourceDay=1,
            sourceOrder=1,
        ),
        UnifiedPlaceCandidate(
            name="Highlands Coffee",
            category="cafe",
            searchRegion="Hà Nội",
            sourceDay=1,
            sourceOrder=2,
        ),
        UnifiedPlaceCandidate(
            name="Nhà thờ Lớn Hà Nội",
            category="attraction",
            searchRegion="Hà Nội",
            sourceDay=1,
            sourceOrder=3,
        ),
    ]

    results = asyncio.run(
        DatabasePlaceResolver(repository).resolve_many(
            candidates,
            destination="Hà Nội",
        )
    )

    assert results[1].status == "resolved"
    assert results[1].external_id == "highlands-near-route"
    assert results[1].resolution_reason == "matched_route_context"


def test_database_resolver_keeps_similarly_close_branches_ambiguous() -> None:
    def place(place_id: str, name: str, longitude: str) -> Any:
        return SimpleNamespace(
            id=place_id,
            name=name,
            place_type="cafe" if "Common" in name else "attraction",
            address="Hoàn Kiếm, Hà Nội",
            city="Hà Nội",
            country="Việt Nam",
            country_code="VN",
            primary_area="Hoàn Kiếm",
            latitude=Decimal("21.0300"),
            longitude=Decimal(longitude),
            data_confidence="high",
            source_fetched_at=datetime.now(timezone.utc),
            metadata_json={},
            region_key="vn,ha-noi",
            status="active",
        )

    repository = FakePlaceRepository(
        [
            place("route-start", "Route Start", "105.8500"),
            place("common-one", "Common Cafe Branch One", "105.8520"),
            place("common-two", "Common Cafe Branch Two", "105.8525"),
            place("route-end", "Route End", "105.8550"),
        ]
    )
    candidates = [
        UnifiedPlaceCandidate(name="Route Start", sourceDay=1, sourceOrder=1),
        UnifiedPlaceCandidate(name="Common Cafe", sourceDay=1, sourceOrder=2),
        UnifiedPlaceCandidate(name="Route End", sourceDay=1, sourceOrder=3),
    ]

    results = asyncio.run(
        DatabasePlaceResolver(repository).resolve_many(
            candidates,
            destination="Hà Nội",
        )
    )

    assert results[1].status == "unresolved"
    assert results[1].resolution_reason == "ambiguous_name"


def test_fallback_chain_does_not_replace_ambiguous_branch_with_provider_guess() -> None:
    def branch(place_id: str, city: str) -> Any:
        return SimpleNamespace(
            id=place_id,
            name="Common Cafe",
            place_type="cafe",
            address=city,
            city=city,
            country="Việt Nam",
            country_code="VN",
            primary_area=None,
            latitude=Decimal("21.0000"),
            longitude=Decimal("105.0000"),
            data_confidence="high",
            source_fetched_at=datetime.now(timezone.utc),
            metadata_json={},
            region_key="vn,ha-noi",
            status="active",
        )

    candidate = UnifiedPlaceCandidate(
        name="Common Cafe",
        category="cafe",
        searchRegion="Hà Nội",
    )
    provider = RecordingFallbackResolver(
        PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="google_maps_scraper",
            name="Common Cafe",
            latitude=Decimal("21.0000"),
            longitude=Decimal("105.0000"),
        )
    )
    resolver = FallbackPlaceResolver(
        DatabasePlaceResolver(
            FakePlaceRepository(
                [
                    branch("common-cafe-one", "Hoàn Kiếm, Hà Nội"),
                    branch("common-cafe-two", "Tây Hồ, Hà Nội"),
                ]
            )
        ),
        provider,
    )

    result = asyncio.run(
        resolver.resolve(candidate, destination="Hà Nội")
    )

    assert result.status == "unresolved"
    assert result.resolution_reason == "ambiguous_name"
    assert provider.calls == 0


def test_fallback_chain_skips_google_when_database_matches() -> None:
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
    google = RecordingFallbackResolver(
        PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="google_maps_scraper",
            name="Phố Đồng Xuân",
            latitude=Decimal("21.0381"),
            longitude=Decimal("105.8490"),
        )
    )
    resolver = FallbackPlaceResolver(database, google)

    result = asyncio.run(resolver.resolve(candidate, destination="Hà Nội"))

    assert result.provider == "database"
    assert database.calls == 1
    assert google.calls == 0


def test_fallback_chain_calls_google_after_database_miss() -> None:
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
    google = RecordingFallbackResolver(
        PlaceResolution(
            candidate=candidate,
            status="resolved",
            provider="google_maps_scraper",
            externalId="ChIJ-test",
            name="Hanoi Train Street",
            latitude=Decimal("21.0180"),
            longitude=Decimal("105.8410"),
        )
    )
    resolver = FallbackPlaceResolver(database, google)

    result = asyncio.run(resolver.resolve(candidate, destination="Hà Nội"))

    assert result.provider == "google_maps_scraper"
    assert database.calls == 1
    assert google.calls == 1


def test_google_maps_rejects_distinct_candidates_with_same_identity() -> None:
    candidates = [
        UnifiedPlaceCandidate(name="SALTPFE", category="cafe", searchRegion="Hanoi"),
        UnifiedPlaceCandidate(name="PURO", category="cafe", searchRegion="Hanoi"),
    ]
    resolver = FakeGoogleMapsScraperResolver(
        {
            "SALTPFE, Hanoi": [{
                "title": "SALTPFE",
                "category": "Cafe",
                "address": "Hanoi, Vietnam",
                "latitude": 20.9977344,
                "longitude": 105.7783808,
            }],
            "PURO, Hanoi": [{
                "title": "PURO",
                "category": "Cafe",
                "address": "Hanoi, Vietnam",
                "latitude": 20.9977344,
                "longitude": 105.7783808,
            }],
        }
    )

    results = asyncio.run(resolver.resolve_many(candidates, destination="unspecified"))

    assert [result.status for result in results] == ["unresolved", "unresolved"]
    assert {
        result.resolution_reason for result in results
    } == {"duplicate_provider_identity"}


def test_google_maps_does_not_query_literal_unspecified() -> None:
    candidate = UnifiedPlaceCandidate(name="Cafe Giảng", searchRegion="unspecified")
    resolver = FakeGoogleMapsScraperResolver({"Cafe Giảng": []})

    asyncio.run(resolver.resolve(candidate, destination="unspecified"))

    assert resolver.queries == ["Cafe Giảng"]
