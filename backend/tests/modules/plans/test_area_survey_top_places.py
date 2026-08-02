from __future__ import annotations

from types import SimpleNamespace

from app.modules.plans.finder.area_survey import StatisticsAreaProfileProvider
from app.modules.plans.finder.place_tool import FinderPlace


class FakePlaceTool:
    def __init__(self, places: list[FinderPlace]) -> None:
        self._places = places

    def get(self, place_id: str) -> FinderPlace | None:
        return next(
            (place for place in self._places if place.place_id == place_id),
            None,
        )

    def search(self, *, region_key: str, limit: int, **kwargs) -> list[FinderPlace]:
        return self.list_region(region_key, limit=limit)

    def list_region(self, region_key: str, *, limit: int) -> list[FinderPlace]:
        return [
            place
            for place in self._places
            if place.region_key == region_key
            or place.region_key.startswith(f"{region_key},")
        ][:limit]


class FakeStatisticsProvider:
    def __init__(self, regions: list[dict]) -> None:
        self.regions = regions

    def get_for_planner(self, region_key: str, *, force: bool = False):
        return SimpleNamespace(regions=self.regions)


def test_profile_prefers_persisted_region_statistics() -> None:
    statistics = FakeStatisticsProvider(
        [
            {
                "regionKey": "vn,hai-phong,cat-ba",
                "plannerEligible": {
                    "countsByType": {"restaurant": 4, "museum": 2},
                    "timeOfDayCoverage": {
                        "morning": 2,
                        "evening": 8,
                        "placesWithKnownHours": 10,
                    },
                    "geographicSummary": {
                        "boundingBox": {
                            "minLatitude": 20.7,
                            "minLongitude": 106.9,
                            "maxLatitude": 20.9,
                            "maxLongitude": 107.1,
                        }
                    },
                },
            }
        ]
    )

    profile = StatisticsAreaProfileProvider(
        FakePlaceTool([]),
        statistics,
    ).get("vn,hai-phong,cat-ba")

    assert profile.distribution == {"food_drink": 4, "attraction": 2}
    assert profile.typical_hours == "evening_focused"
    assert profile.bbox == (20.7, 106.9, 20.9, 107.1)
    assert profile.estimated_walkability == "unknown"


def test_profile_falls_back_to_strict_catalog_region() -> None:
    local = FinderPlace(
        placeId="local",
        name="Local museum",
        placeType="museum",
        regionKey="vn,ha-noi,cua-nam",
        latitude=21.025,
        longitude=105.846,
    )
    other_area = FinderPlace(
        placeId="other",
        name="Other restaurant",
        placeType="restaurant",
        regionKey="vn,ha-noi,duong-noi",
        latitude=20.998,
        longitude=105.752,
    )

    profile = StatisticsAreaProfileProvider(
        FakePlaceTool([local, other_area])
    ).get("vn,ha-noi,cua-nam")

    assert profile.distribution == {"attraction": 1}
    assert profile.bbox == (21.025, 105.846, 21.025, 105.846)
    assert profile.estimated_walkability == "unknown"
