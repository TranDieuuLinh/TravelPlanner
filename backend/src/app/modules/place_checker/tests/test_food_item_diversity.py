from app.modules.place_checker.selection.food.item_diversity import (
    select_food_item_candidates,
)
from app.modules.place_checker.tests.test_food_selection import candidate


def _rank(item, _priors):
    return (item.food_priority, -item.distance_km, item.restaurant_id)


def test_cycles_distinct_food_items_before_reusing_one() -> None:
    candidates = [
        candidate("area:a", "restaurant:pho:1", food="food:pho"),
        candidate("area:a", "restaurant:bun:1", food="food:bun-cha"),
        candidate("area:b", "restaurant:pho:2", food="food:pho"),
        candidate("area:b", "restaurant:bun:2", food="food:bun-cha"),
    ]

    selected = select_food_item_candidates(candidates, 1, {}, _rank)

    assert selected[0].food_item_id != selected[1].food_item_id
    assert len({item.restaurant_id for item in selected}) == 4


def test_balances_food_item_selection_across_real_anchors() -> None:
    candidates = [
        candidate("area:a", "restaurant:a:1", food="food:pho"),
        candidate("area:a", "restaurant:a:2", food="food:bun-cha"),
        candidate("area:b", "restaurant:b:1", food="food:pho"),
        candidate("area:b", "restaurant:b:2", food="food:bun-cha"),
    ]

    selected = select_food_item_candidates(candidates, 1, {}, _rank)

    assert selected[0].anchor_place_id != selected[1].anchor_place_id
    assert [item.anchor_place_id for item in selected].count("area:a") == 2
    assert [item.anchor_place_id for item in selected].count("area:b") == 2


def test_has_style_does_not_change_food_item_selection() -> None:
    styled = candidate(
        "area:a",
        "restaurant:a",
        food="food:pho",
        style_id="style_breakfast",
        style_name="Ăn sáng",
    )

    selected = select_food_item_candidates([styled], 1, {}, _rank)

    assert [item.restaurant_id for item in selected] == ["restaurant:a"]


def test_food_item_diversity_precedes_repeating_a_higher_ranked_item() -> None:
    candidates = [
        candidate("place:a", "restaurant:pho-a", food="food:pho", priority=0.99),
        candidate("place:b", "restaurant:pho-b", food="food:pho", priority=0.98),
        candidate(
            "place:c",
            "restaurant:bun-cha",
            food="food:bun-cha",
            priority=0.50,
        ),
    ]

    selected = select_food_item_candidates(
        candidates,
        days=1,
        priors={},
        rank=lambda item, _priors: (item.food_priority,),
    )

    assert len({item.restaurant_id for item in selected}) == len(selected)
    assert {item.food_item_id for item in selected[:2]} == {
        "food:pho",
        "food:bun-cha",
    }
