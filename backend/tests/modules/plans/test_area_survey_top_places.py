from __future__ import annotations

from app.modules.plans.finder.area_survey import AreaSurveyResult, AreaSurveyService
from app.modules.plans.finder.place_tool import FinderPlace


class FakePlaceTool:
    """Minimal FinderPlaceTool stub for AreaSurveyService tests."""

    def __init__(self, places: list[FinderPlace]) -> None:
        self._places = places

    def get(self, place_id: str) -> FinderPlace | None:
        for place in self._places:
            if place.place_id == place_id:
                return place
        return None

    def search(
        self,
        *,
        region_key: str,
        target_tags: list[str],
        target_categories: set[str] | None = None,
        excluded_place_ids: set[str],
        limit: int,
    ) -> list[FinderPlace]:
        return [
            place
            for place in self._places
            if place.region_key == region_key
            and place.place_id not in excluded_place_ids
        ][:limit]


def _make_place(
    place_id: str,
    name: str,
    rating: float | None = None,
    review_count: int = 0,
) -> FinderPlace:
    return FinderPlace(
        placeId=place_id,
        name=name,
        placeType="attraction",
        regionKey="vn,hai-phong,cat-ba",
        rating=rating,
        reviewCount=review_count,
    )


def test_survey_returns_two_separate_top_lists() -> None:
    places = [
        _make_place("p1", "A", rating=4.8, review_count=10),
        _make_place("p2", "B", rating=4.5, review_count=900),
        _make_place("p3", "C", rating=None, review_count=5000),
        _make_place("p4", "D", rating=4.2, review_count=200),
    ]
    service = AreaSurveyService(FakePlaceTool(places))

    result = service.survey("vn,hai-phong,cat-ba")

    assert isinstance(result, AreaSurveyResult)
    # top_places_by_rating: places có rating thật xếp trước, p3 (no rating) ở cuối.
    assert [p.place_id for p in result.top_places_by_rating] == ["p1", "p2", "p4", "p3"]
    # top_places_by_reviews: sắp theo review_count, p2 có rating cao hơn p4 đứng trước.
    assert [p.place_id for p in result.top_places_by_reviews] == ["p3", "p2", "p4", "p1"]


def test_survey_top_places_filter_out_place_without_id() -> None:
    places = [
        _make_place("p1", "A", rating=4.8, review_count=10),
        _make_place("p2", "B", rating=4.9, review_count=5),
        FinderPlace(
            placeId=None,
            name="NoId",
            placeType="attraction",
            regionKey="vn,hai-phong,cat-ba",
            rating=5.0,
            reviewCount=9999,
        ),
    ]
    service = AreaSurveyService(FakePlaceTool(places))

    result = service.survey("vn,hai-phong,cat-ba")

    place_ids_rating = {p.place_id for p in result.top_places_by_rating}
    place_ids_reviews = {p.place_id for p in result.top_places_by_reviews}
    assert place_ids_rating == {"p1", "p2"}
    assert place_ids_reviews == {"p1", "p2"}
    assert all(p.place_id is not None for p in result.top_places_by_rating)
    assert all(p.place_id is not None for p in result.top_places_by_reviews)


def test_survey_applies_top_places_limit() -> None:
    places = [
        _make_place(f"p{i}", f"P{i}", rating=4.0 + i * 0.01, review_count=i)
        for i in range(1, 16)
    ]
    service = AreaSurveyService(FakePlaceTool(places))

    result = service.survey("vn,hai-phong,cat-ba")

    assert len(result.top_places_by_rating) == AreaSurveyService.TOP_PLACES_LIMIT == 10
    assert len(result.top_places_by_reviews) == AreaSurveyService.TOP_PLACES_LIMIT == 10


def test_survey_empty_region_returns_empty_lists() -> None:
    service = AreaSurveyService(FakePlaceTool([]))

    result = service.survey("vn,empty")

    assert result.top_places_by_rating == ()
    assert result.top_places_by_reviews == ()


def test_survey_bbox_excludes_parent_scope_fallback_places() -> None:
    local = FinderPlace(
        placeId="local",
        name="Cửa Nam local",
        placeType="restaurant",
        regionKey="vn,ha-noi,cua-nam",
        latitude=21.025,
        longitude=105.846,
    )
    far_parent_fallback = FinderPlace(
        placeId="far",
        name="Dương Nội fallback",
        placeType="restaurant",
        regionKey="vn,ha-noi,duong-noi",
        latitude=20.998,
        longitude=105.752,
    )

    class WideningPlaceTool(FakePlaceTool):
        def search(self, **kwargs) -> list[FinderPlace]:
            return [local, far_parent_fallback]

    result = AreaSurveyService(
        WideningPlaceTool([local, far_parent_fallback])
    ).survey("vn,ha-noi,cua-nam")

    assert result.profile.place_count == 1
    assert result.profile.bbox == (21.025, 105.846, 21.025, 105.846)


def test_survey_top_by_rating_drops_missing_rating_to_bottom() -> None:
    places = [
        _make_place("no_rating", "X", rating=None, review_count=10000),
        _make_place("r1", "R1", rating=4.0, review_count=10),
        _make_place("r2", "R2", rating=4.5, review_count=20),
    ]
    service = AreaSurveyService(FakePlaceTool(places))

    result = service.survey("vn,hai-phong,cat-ba")

    assert [p.place_id for p in result.top_places_by_rating] == ["r2", "r1", "no_rating"]
    assert [p.place_id for p in result.top_places_by_reviews] == ["no_rating", "r2", "r1"]


def test_survey_top_by_rating_tiebreak_uses_review_count_then_name() -> None:
    places = [
        _make_place("a", "Zeta", rating=4.5, review_count=10),
        _make_place("b", "Beta", rating=4.5, review_count=10),
        _make_place("c", "Alpha", rating=4.5, review_count=10),
    ]
    service = AreaSurveyService(FakePlaceTool(places))

    result = service.survey("vn,hai-phong,cat-ba")

    assert [p.name for p in result.top_places_by_rating] == ["Alpha", "Beta", "Zeta"]


def test_survey_top_by_reviews_tiebreak_uses_rating_then_name() -> None:
    places = [
        _make_place("a", "Zeta", rating=4.0, review_count=100),
        _make_place("b", "Beta", rating=4.5, review_count=100),
        _make_place("c", "Alpha", rating=3.5, review_count=100),
    ]
    service = AreaSurveyService(FakePlaceTool(places))

    result = service.survey("vn,hai-phong,cat-ba")

    assert [p.name for p in result.top_places_by_reviews] == ["Beta", "Zeta", "Alpha"]
