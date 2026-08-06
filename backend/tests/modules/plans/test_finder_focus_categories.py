"""Regression tests for the user-facing case::

    "Hà Nội cuối tuần, ưu tiên món địa phương và văn hóa"

These tests pin down the classification bug we just fixed: the
``SEMANTIC_CATEGORY_TERMS['attraction']`` set used to contain
generic phrases like ``"khai quat"`` / ``"explore"`` / ``"discover"``
and region phrases like ``"pho co"``. That made queries about
"khám phá ẩm thực phố cổ" leak into the ``attraction`` semantic
category and let unrelated museums outrank restaurants in the
food-focused day. The tests below guard against the regression.
"""

from __future__ import annotations

import pytest

from app.modules.places.model import Place
from app.modules.plans.place_selector.place_tool import (
    SelectablePlace,
    SEMANTIC_CATEGORY_TERMS,
    _normalized_terms,
    place_category,
    semantic_categories,
)


# ---------------------------------------------------------------------------
# Unit: SEMANTIC_CATEGORY_TERMS purity
# ---------------------------------------------------------------------------


def test_attraction_does_not_contain_generic_explore_words() -> None:
    """Generic phrases must not live in the attraction synonym set.

    Including words like ``"khai quat"``, ``"explore"``, ``"discover"``
    caused the "khám phá ẩm thực phố cổ" query to be classified as an
    attraction request and let unrelated museums outrank restaurants.
    """

    attraction = SEMANTIC_CATEGORY_TERMS["attraction"]
    leaks = {
        word for word in ("khai quat", "explore", "discover")
        if word in attraction
    }
    assert not leaks, (
        "Generic attraction keywords should be removed: "
        f"{leaks!r}"
    )


def test_attraction_does_not_contain_region_phrase_pho_co() -> None:
    """Region phrases like "phố cổ" are not a category on their own.

    A query about "khám phá ẩm thực phố cổ" mistakenly picked up
    ``attraction`` via this token, biasing candidate selection away
    from food.
    """

    attraction = SEMANTIC_CATEGORY_TERMS["attraction"]
    assert "pho co" not in attraction


# ---------------------------------------------------------------------------
# Unit: ``semantic_categories`` for the user query
# ---------------------------------------------------------------------------


def test_user_query_maps_only_food_drink() -> None:
    """``semantic_categories`` for the user's food query must be ``food_drink``.

    The query "food + 'Khám phá ẩm thực phố cổ' + 'Hoàn Kiếm'" should
    resolve to ``food_drink`` only. Any ``attraction`` leak means the
    search pool will include museums.
    """

    terms = _normalized_terms([
        "food",
        "Khám phá ẩm thực phố cổ",
        "Hoàn Kiếm",
    ])
    categories = semantic_categories(terms)

    assert "food_drink" in categories
    assert "attraction" not in categories, (
        "Query phrased around food must not leak into attraction; "
        f"got {categories!r}"
    )


def test_cafe_is_an_activity_category_not_a_meal_category() -> None:
    categories = semantic_categories({"cafe", "coffee"})

    assert categories == {"attraction"}
    assert place_category(
        SelectablePlace(
            placeId="cafe-dinh",
            name="Cafe Đinh",
            placeType="cafe",
            regionKey="vn,ha-noi",
            tags=["cafe", "coffee"],
        )
    ) == "attraction"


@pytest.mark.parametrize(
    "place_type",
    ["Ice cream shop", "Dessert shop", "Juice shop", "Tea shop"],
)
def test_provider_food_shop_variants_cannot_fill_activity_slots(place_type: str) -> None:
    assert place_category(
        SelectablePlace(
            name="Provider food venue",
            placeType=place_type,
            regionKey="vn,ha-noi",
        )
    ) == "food_drink"


@pytest.mark.parametrize(
    "name,place_type",
    [
        ("L7 West Lake Hanoi", "Hotel"),
        ("Minerva Church Hotel", "Hotel"),
        ("West Lake Homestay Apartments", "Homestay"),
        ("Ngõ Nhà Thờ", "Apartment building"),
    ],
)
def test_accommodation_type_overrides_landmark_words(
    name: str,
    place_type: str,
) -> None:
    assert place_category(
        SelectablePlace(
            name=name,
            placeType=place_type,
            regionKey="vn,ha-noi",
        )
    ) == "accommodation"


def test_restaurant_type_overrides_landmark_words() -> None:
    assert place_category(
        SelectablePlace(
            name="West Lake Culture Restaurant",
            placeType="Restaurant",
            regionKey="vn,ha-noi",
        )
    ) == "food_drink"


def test_landmark_name_overrides_food_tag_from_url_activity_evidence() -> None:
    assert place_category(
        SelectablePlace(
            name="Nhà thờ Lớn Hà Nội",
            placeType="selected_place",
            regionKey="vn,ha-noi",
            tags=["food"],
        )
    ) == "attraction"


# ---------------------------------------------------------------------------
# Integration: search() over the food query returns only food places
# ---------------------------------------------------------------------------


class _ListRepo:
    def __init__(self, places: list[Place]) -> None:
        self._by_id: dict[str, Place] = {}
        for place in places:
            for region in self._enumerate_regions(place.region_key):
                self._by_id.setdefault(region + ":" + place.id, place)
        self._by_region: dict[str, list[Place]] = {}
        for place in places:
            for region in self._enumerate_regions(place.region_key):
                self._by_region.setdefault(region, []).append(place)

    @staticmethod
    def _enumerate_regions(region_key: str) -> list[str]:
        parts = region_key.split(",")
        return [
            ",".join(parts[:length])
            for length in range(len(parts), 0, -1)
        ]

    def get(self, place_id: str) -> Place | None:
        return next(
            (p for p in self._by_id.values() if p.id == place_id),
            None,
        )

    def list_for_place_selection(
        self,
        region_key: str,
        *,
        limit: int = 10000,
    ) -> list[Place]:
        return list(self._by_region.get(region_key, []))[:limit]


def _make_place(
    place_id: str,
    name: str,
    place_type: str,
    *,
    place_group: str,
    tags: tuple[str, ...],
) -> Place:
    return Place(
        id=place_id,
        name=name,
        place_type=place_type,
        region_key="vn,ha-noi,hoan-kiem",
        data_confidence="high",
        metadata_json={"placeGroup": place_group, "tags": list(tags)},
    )


def test_search_food_query_does_not_return_museums() -> None:
    """Mimicking the search call done for the user's ``main_activity`` slot.

    The query string mirrors what the Finder built for the
    "khám phá ẩm thực phố cổ" day. Museums and temples must not
    surface in the result list - the user asked for food.
    """

    from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool

    places = [
        _make_place(
            "p_pho", "Phở Thìn Bờ Hồ", "restaurant",
            place_group="food_drink", tags=("food", "local_cuisine"),
        ),
        _make_place(
            "p_buncha", "Bún Chả Đắc Kim", "restaurant",
            place_group="food_drink", tags=("food", "local_cuisine"),
        ),
        _make_place(
            "p_hkg", "Hồ Hoàn Kiếm", "attraction",
            place_group="attraction", tags=("culture",),
        ),
        _make_place(
            "p_vm", "Văn Miếu Quốc Tử Giám", "museum",
            place_group="attraction", tags=("culture", "history"),
        ),
        _make_place(
            "p_dq", "Đền Quán Thánh", "temple",
            place_group="attraction", tags=("culture", "spiritual"),
        ),
    ]
    tool = RepositoryPlaceSelectionTool(_ListRepo(places))

    result = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=["food", "Khám phá ẩm thực phố cổ", "Hoàn Kiếm"],
        excluded_place_ids=set(),
        limit=10,
    )

    # The user asked for food. Culture places must not appear.
    cultural_ids = {"p_hkg", "p_vm", "p_dq"}
    result_ids = {p.place_id for p in result}
    leaked = cultural_ids & result_ids
    assert not leaked, (
        f"Food query leaked culture places: {leaked!r}"
    )

    # And food places must appear.
    food_ids = {"p_pho", "p_buncha"}
    assert food_ids & result_ids, (
        "Expected food places to be returned for a food query"
    )


def test_search_food_query_excludes_non_dining_food_businesses_before_limit() -> None:
    from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool

    places = [
        *[
            _make_place(
                f"supplier-{index}",
                f"Food supplier {index}",
                "Catering food and drink supplier",
                place_group="food_drink",
                tags=("food", "breakfast"),
            )
            for index in range(20)
        ],
        _make_place(
            "restaurant",
            "Phở Hà Nội",
            "Vietnamese restaurant",
            place_group="food_drink",
            tags=("food", "breakfast"),
        ),
    ]
    tool = RepositoryPlaceSelectionTool(_ListRepo(places))

    result = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=["breakfast", "food"],
        excluded_place_ids=set(),
        limit=1,
    )

    assert [place.place_id for place in result] == ["restaurant"]


def test_search_culture_query_excludes_cafes_before_ranking() -> None:
    from app.modules.plans.place_selector.place_tool import RepositoryPlaceSelectionTool

    places = [
        _make_place(
            "p_cafe", "Hanoi Coffee Culture", "Coffee shop",
            place_group="attraction", tags=("cafe", "culture"),
        ),
        _make_place(
            "p_restaurant", "Culture Restaurant", "restaurant",
            place_group="food_drink", tags=("food", "culture"),
        ),
        _make_place(
            "p_museum", "Bảo tàng Hà Nội", "museum",
            place_group="attraction", tags=("culture", "history"),
        ),
        _make_place(
            "p_temple", "Đền Quán Thánh", "temple",
            place_group="attraction", tags=("culture", "spiritual"),
        ),
    ]
    tool = RepositoryPlaceSelectionTool(_ListRepo(places))

    result = tool.search(
        region_key="vn,ha-noi,hoan-kiem",
        target_tags=["culture", "history", "sightseeing"],
        excluded_place_ids=set(),
        limit=10,
    )

    assert {place.place_id for place in result} == {"p_museum", "p_temple"}
