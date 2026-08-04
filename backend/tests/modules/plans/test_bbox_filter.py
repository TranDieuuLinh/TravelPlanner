"""Tests for the bounding-box pre-filter inside the Finder place tool.

When the AreaSurveyService has computed a bbox for the target region, the
tool uses it to drop candidates that fall outside it. The bbox is opt-in:
omitting it falls back to the existing string-based region-key match.
"""

from __future__ import annotations

from app.modules.plans.finder.place_tool import (
    EmptyFinderPlaceTool,
    FinderPlace,
    RepositoryFinderPlaceTool,
    _inside_bbox,
)
from app.modules.places.model import Place


# ---------------------------------------------------------------------------
# Unit: ``_inside_bbox`` predicate
# ---------------------------------------------------------------------------


def _place(lat: float | None, lon: float | None) -> FinderPlace:
    return FinderPlace(
        name="probe",
        placeType="attraction",
        regionKey="vn,ha-noi",
        latitude=lat,
        longitude=lon,
    )


def test_inside_bbox_returns_true_for_place_inside() -> None:
    bbox = (21.0, 105.0, 21.1, 105.2)
    assert _inside_bbox(_place(21.05, 105.1), bbox) is True


def test_inside_bbox_returns_false_for_place_outside() -> None:
    bbox = (21.0, 105.0, 21.1, 105.2)
    assert _inside_bbox(_place(21.5, 105.5), bbox) is False


def test_inside_bbox_keeps_places_without_coordinates() -> None:
    bbox = (21.0, 105.0, 21.1, 105.2)
    assert _inside_bbox(_place(None, None), bbox) is True


# ---------------------------------------------------------------------------
# Integration: RepositoryFinderPlaceTool.search applies bbox
# ---------------------------------------------------------------------------


class _ListRepo:
    """In-memory FinderPlaceRepository stub for the tool."""

    def __init__(self, places: list[Place]) -> None:
        self._by_id = {p.id: p for p in places if p.id}

    def get(self, place_id: str) -> Place | None:
        return self._by_id.get(place_id)

    def list_for_finder(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Place]:
        return [
            p for p in self._by_id.values()
            if region_key in p.region_key
        ][:limit]


def _fixture_place(
    place_id: str,
    region: str,
    *,
    lat: float | None,
    lon: float | None,
    name: str = "p",
) -> Place:
    place = Place(
        id=place_id,
        name=name,
        place_type="attraction",
        region_key=region,
        data_confidence="high",
    )
    place.latitude = lat
    place.longitude = lon
    place.metadata_json = {}
    place.opening_hours = []
    place.typical_duration_minutes = None
    return place


# Hoàn Kiếm bbox ~ (21.01, 105.84, 21.05, 105.86)
HANOI_BBOX = (21.01, 105.84, 21.05, 105.86)
LONG_BIEN_BBOX = (21.02, 105.87, 21.06, 105.90)


def test_search_drops_places_outside_bbox() -> None:
    in_hoan_kiem = _fixture_place(
        "in-hk", "vn,ha-noi,hoan-kiem",
        lat=21.03, lon=105.85, name="Hoan Kiem place",
    )
    in_long_bien = _fixture_place(
        "in-lb", "vn,ha-noi,long-bien",
        lat=21.04, lon=105.88, name="Long Bien place",
    )
    no_coords = _fixture_place(
        "no-coords", "vn,ha-noi,hoan-kiem",
        lat=None, lon=None, name="Missing coordinates",
    )

    tool = RepositoryFinderPlaceTool(_ListRepo([in_hoan_kiem, in_long_bien, no_coords]))

    result = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=[],
        excluded_place_ids=set(),
        limit=10,
        bbox_filter=HANOI_BBOX,
    )

    place_ids = {p.place_id for p in result}
    assert "in-hk" in place_ids
    assert "in-lb" not in place_ids
    assert "no-coords" in place_ids


def test_search_without_bbox_falls_back_to_region_match() -> None:
    in_hoan_kiem = _fixture_place(
        "in-hk", "vn,ha-noi,hoan-kiem",
        lat=21.03, lon=105.85, name="HK",
    )
    in_long_bien = _fixture_place(
        "in-lb", "vn,ha-noi,long-bien",
        lat=21.04, lon=105.88, name="LB",
    )

    tool = RepositoryFinderPlaceTool(_ListRepo([in_hoan_kiem, in_long_bien]))

    result = tool.search(
        region_key="vn,ha-noi",
        target_tags=[],
        excluded_place_ids=set(),
        limit=10,
    )

    place_ids = {p.place_id for p in result}
    assert "in-hk" in place_ids
    assert "in-lb" in place_ids


def test_search_bbox_with_no_matches_returns_empty() -> None:
    far_away = _fixture_place(
        "far", "vn,ha-noi,hoan-kiem",
        lat=21.5, lon=105.5, name="Far",
    )
    tool = RepositoryFinderPlaceTool(_ListRepo([far_away]))

    result = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=[],
        excluded_place_ids=set(),
        limit=10,
        bbox_filter=HANOI_BBOX,
    )

    assert result == []


def test_empty_tool_accepts_bbox_filter_kwarg() -> None:
    result = EmptyFinderPlaceTool().search(
        region_key="vn,ha-noi",
        target_tags=[],
        excluded_place_ids=set(),
        limit=10,
        bbox_filter=HANOI_BBOX,
    )
    assert result == []
