from app.modules.place_checker.food_item_diversity import (
    FOOD_DRINK_STYLES,
    select_style_item_candidates,
)
from app.modules.place_checker.tests.test_food_selection import candidate


def _rank(item, _priors):
    return (item.food_priority, -item.distance_km, item.restaurant_id)


def _styled(anchor: str, restaurant: str, food: str):
    return candidate(
        anchor,
        restaurant,
        food=food,
        style_id="style_breakfast",
        style_name="Ăn sáng",
    )


def test_cycles_distinct_items_before_reusing_item_in_same_region() -> None:
    candidates = [
        _styled("area:hoan-kiem", "restaurant:pho:1", "food:pho"),
        _styled("area:hoan-kiem", "restaurant:bun:1", "food:bun-cha"),
        _styled("area:hoan-kiem", "restaurant:pho:2", "food:pho"),
        _styled("area:hoan-kiem", "restaurant:bun:2", "food:bun-cha"),
    ]

    selected, coverage = select_style_item_candidates(
        candidates, days=2, priors={}, rank=_rank
    )

    assert selected[0].food_item_id != selected[1].food_item_id
    assert [item.food_item_id for item in selected].count("food:pho") == 2
    assert [item.food_item_id for item in selected].count("food:bun-cha") == 2
    breakfast = next(item for item in coverage if item.style_id == "style_breakfast")
    assert breakfast.target_items == 4
    assert breakfast.selected_restaurants == 4
    assert breakfast.distinct_items == 2
    assert breakfast.complete is True


def test_balances_style_selection_across_anchor_regions() -> None:
    candidates = [
        _styled("area:a", "restaurant:a:1", "food:pho"),
        _styled("area:a", "restaurant:a:2", "food:bun-cha"),
        _styled("area:b", "restaurant:b:1", "food:pho"),
        _styled("area:b", "restaurant:b:2", "food:bun-cha"),
    ]

    selected, _ = select_style_item_candidates(
        candidates, days=2, priors={}, rank=_rank
    )

    assert [item.anchor_place_id for item in selected] == [
        "area:a",
        "area:b",
        "area:a",
        "area:b",
    ]
    assert len({item.restaurant_id for item in selected}) == 4


def test_reports_all_active_food_drink_styles_when_catalog_supports_styles() -> None:
    selected, coverage = select_style_item_candidates(
        [_styled("area:a", "restaurant:a", "food:pho")],
        days=1,
        priors={},
        rank=_rank,
    )

    assert len(selected) == 1
    assert {item.style_id for item in coverage} == set(FOOD_DRINK_STYLES)
    assert next(
        item for item in coverage if item.style_id == "style_breakfast"
    ).selected_restaurants == 1
    assert next(
        item for item in coverage if item.style_id == "style_nightlife"
    ).selected_restaurants == 0
