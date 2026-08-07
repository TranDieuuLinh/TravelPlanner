from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest

from app.modules.places.auto_statistics.domain import (
    PlaceStatisticsRecord,
    build_region_statistics,
)
from app.modules.places.auto_statistics.service import AutoPlaceStatisticsService


def test_statistics_roll_up_regions_and_separate_mock_prices() -> None:
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    places = [
        PlaceStatisticsRecord(
            id="place-1",
            region_key="vn,da-nang,hai-chau",
            place_type="museum",
            status="active",
            latitude=16.06,
            longitude=108.22,
            opening_hours=[
                {
                    "openTime": "08:00",
                    "closeTime": "17:00",
                    "is24Hours": False,
                    "provenance": {"isMock": True},
                }
            ],
            typical_duration_minutes=120,
            data_confidence="medium",
            source_fetched_at=now,
            metadata={
                "tags": [
                    "cafe",
                    "coffee_shop",
                    "food",
                    "Restaurant",
                    "0987654321",
                ],
                "placeGroup": "Restaurant",
                "indoorOutdoor": "indoor",
                "weatherSensitivity": "low",
                "bookingRequired": False,
                "prices": [{"amountMin": 40000, "isMock": False}],
            },
        ),
        PlaceStatisticsRecord(
            id="place-2",
            region_key="vn,da-nang,hai-chau",
            place_type="cafe",
            status="active",
            latitude=None,
            longitude=None,
            opening_hours=[],
            typical_duration_minutes=60,
            data_confidence="low",
            source_fetched_at=now - timedelta(days=60),
            metadata={
                "tags": ["museum", "culture"],
                "placeGroup": "attraction",
                "indoorOutdoor": "indoor",
                "weatherSensitivity": "low",
                "bookingRequired": True,
                "prices": [{"amountMin": 50000, "isMock": True}],
            },
        ),
    ]

    regions, row_count = build_region_statistics(
        places,
        stale_before=now - timedelta(days=30),
    )

    assert row_count == 2
    assert [region["regionKey"] for region in regions] == [
        "vn,da-nang",
        "vn,da-nang,hai-chau",
    ]
    city = regions[0]
    assert city["placeCount"] == 2
    assert city["countsByType"] == {"cafe": 1, "museum": 1}
    assert city["timeOfDayCoverage"]["morning"] == 1
    assert city["timeOfDayCoverage"]["afternoon"] == 1
    assert city["dataQuality"]["missingCoordinates"] == 1
    assert city["dataQuality"]["staleOperationalData"] == 1
    assert city["dataQuality"]["placesUsingMockOpeningHours"] == 1
    assert city["tagCounts"] == {
        "coffee": 1,
        "culture": 1,
        "food": 1,
    }
    assert city["tagTimeCoverage"]["coffee"]["morning"] == 1
    assert city["tagTimeCoverage"]["coffee"]["afternoon"] == 1
    assert city["tagDurationProfile"]["culture"] == {
        "medianMinutes": 60,
        "sampleSize": 1,
    }
    assert city["placeGroupCounts"] == {"Restaurant": 1, "attraction": 1}
    assert city["bookingRequirementCounts"] == {
        "required": 1,
        "notRequired": 1,
        "unknown": 0,
    }
    assert city["plannerSignals"]["dominantTags"] == [
        "coffee",
        "culture",
        "food",
    ]
    assert city["areaProfiles"][0]["regionKey"] == "vn,da-nang,hai-chau"
    assert city["areaProfiles"][0]["topTags"] == ["coffee", "culture", "food"]
    assert city["priceCoverage"] == {
        "placesWithAnyPrice": 2,
        "placesWithVerifiedPrice": 1,
        "placesWithOnlyMockPrices": 1,
    }


def test_service_skips_refresh_when_source_is_unchanged(tmp_path: Path) -> None:
    output_path = tmp_path / "generated" / "statistics.json"
    repository = FakePlaceStatisticsRepository([_example_place()])
    service = AutoPlaceStatisticsService(
        repository,
        output_path,
        stale_after_days=30,
    )

    first = service.refresh()
    first_content = output_path.read_text(encoding="utf-8")
    second = service.refresh()

    assert first.status == "refreshed"
    assert second.status == "unchanged"
    assert output_path.read_text(encoding="utf-8") == first_content
    payload = json.loads(first_content)
    assert payload["source"]["rowCount"] == 1
    assert payload["regions"][0]["regionKey"] == "vn,ha-noi"


def test_planner_statistics_are_computed_without_database_snapshots(
    tmp_path: Path,
) -> None:
    repository = FakePlaceStatisticsRepository([_example_place()])
    service = AutoPlaceStatisticsService(
        repository,
        tmp_path / "statistics.json",
    )

    first = service.get_for_planner("vn,ha-noi")
    second = service.get_for_planner("vn,ha-noi")

    assert first.status == "computed"
    assert first.snapshot_id == second.snapshot_id
    assert first.catalog_version == second.catalog_version
    assert first.snapshot_id.startswith("live-")


def test_planner_can_read_a_fresh_generated_snapshot_without_scanning_repository(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "statistics.json"
    repository = FakePlaceStatisticsRepository([_example_place()])
    writer = AutoPlaceStatisticsService(repository, output_path)
    writer.refresh()

    class RepositoryThatMustNotBeRead:
        def source_signature(self, region_key=None):
            raise AssertionError("planner should use the generated snapshot")

        def iter_statistics_records(self, region_key=None):
            raise AssertionError("planner should use the generated snapshot")

    reader = AutoPlaceStatisticsService(
        RepositoryThatMustNotBeRead(),
        output_path,
        prefer_snapshot_for_planner=True,
    )

    result = reader.get_for_planner("vn,ha-noi")

    assert result.status == "snapshot"
    assert result.regions[0]["regionKey"] == "vn,ha-noi"
    assert result.snapshot_id.startswith("snapshot-")


def test_statistics_reject_invalid_region_key() -> None:
    place = _example_place(region_key="ha-noi")

    with pytest.raises(ValueError, match="Invalid region_key"):
        build_region_statistics(
            [place],
            stale_before=datetime(2026, 6, 27, tzinfo=timezone.utc),
        )


def test_planner_signals_use_active_places_at_smallest_available_area() -> None:
    now = datetime(2026, 7, 27, tzinfo=timezone.utc)
    active = _example_place(region_key="vn,da-nang,son-tra,an-hai")
    active = PlaceStatisticsRecord(
        **{
            **active.__dict__,
            "status": "active",
            "metadata": {"tags": ["beach", "nature"]},
        }
    )
    inactive = _example_place(region_key="vn,da-nang,hai-chau")
    inactive = PlaceStatisticsRecord(
        **{
            **inactive.__dict__,
            "id": "inactive-place",
            "status": "inactive",
            "metadata": {"tags": ["nightclub"]},
        }
    )

    regions, _ = build_region_statistics(
        [active, inactive],
        stale_before=now - timedelta(days=30),
    )

    city = next(region for region in regions if region["regionKey"] == "vn,da-nang")
    assert city["plannerSignals"]["statisticsLevel"] == (
        "smallest_available_region"
    )
    assert city["plannerSignals"]["dominantTags"] == ["nature"]
    assert city["plannerSignals"]["candidateAreas"] == [
        {
            "regionKey": "vn,da-nang,son-tra,an-hai",
            "placeCount": 1,
            "topTags": ["nature"],
        }
    ]
    assert city["areaProfiles"][0]["geographicSummary"]["centroid"] is not None


class FakePlaceStatisticsRepository:
    def __init__(self, places: list[PlaceStatisticsRecord]) -> None:
        self.places = places

    def source_signature(
        self,
        region_key: str | None = None,
    ) -> dict[str, str | int]:
        return {
            "storage": "fake",
            "regionKey": region_key or "*",
            "fingerprint": f"fake-{len(self.places)}",
            "rowCount": len(self.places),
            "revisionSum": len(self.places),
            "maxUpdatedAt": "2026-07-27T00:00:00+00:00",
        }

    def iter_statistics_records(
        self,
        region_key: str | None = None,
    ) -> Iterator[PlaceStatisticsRecord]:
        for place in self.places:
            if region_key is None or (
                place.region_key == region_key
                or place.region_key.startswith(f"{region_key},")
            ):
                yield place


def _example_place(
    *,
    region_key: str = "vn,ha-noi",
) -> PlaceStatisticsRecord:
    return PlaceStatisticsRecord(
        id="place-1",
        region_key=region_key,
        place_type="attraction",
        status="active",
        latitude=21.0,
        longitude=105.8,
        opening_hours=[],
        typical_duration_minutes=90,
        data_confidence="medium",
        source_fetched_at=datetime(2026, 7, 26, tzinfo=timezone.utc),
        metadata={"description": "Example", "prices": []},
    )
