from app.modules.place_checker.selection.food.meal_matching import build_food_meal_coverage
from app.modules.place_checker.selection.food.pool_policy import aggregate_restaurants
from app.modules.place_checker.tests.test_food_selection import candidate


def _with_hours(restaurant_id: str, hours: str):
    value = candidate("place:anchor", restaurant_id)
    return value.model_copy(
        update={
            "metadata": value.metadata.model_copy(update={"opening_hours": [hours]})
        }
    )


def _coverage(values, days: int):
    def rank(item, _):
        return (item.restaurant_id,)

    aggregates = aggregate_restaurants(values, {}, rank)
    return build_food_meal_coverage(
        aggregates,
        days,
        lambda item: (item.best.restaurant_id,),
    )


def test_unique_matching_detects_count_only_false_positive() -> None:
    values = [
        *(_with_hours(f"restaurant:all:{index}", "07:00-21:00") for index in range(3)),
        *(
            _with_hours(f"restaurant:dinner:{index}", "17:00-21:00")
            for index in range(6)
        ),
    ]

    coverage = _coverage(values, days=3)

    assert len(values) == 9
    assert coverage.hard_complete is False
    assert len(coverage.hard_assignments) == 6
    assert len(coverage.hard_missing_slots) == 3
    assert {slot.meal for slot in coverage.hard_missing_slots} <= {
        "breakfast",
        "lunch",
    }


def test_unique_matching_completes_one_restaurant_per_meal_slot() -> None:
    values = [
        *(
            _with_hours(f"restaurant:breakfast:{index}", "06:00-10:00")
            for index in range(3)
        ),
        *(
            _with_hours(f"restaurant:lunch:{index}", "11:00-14:00")
            for index in range(3)
        ),
        *(
            _with_hours(f"restaurant:dinner:{index}", "17:00-21:00")
            for index in range(3)
        ),
    ]

    coverage = _coverage(values, days=3)

    assert coverage.hard_complete is True
    assert len(coverage.hard_assignments) == 9
    assert len({item.restaurant_id for item in coverage.hard_assignments}) == 9
    assert coverage.hard_missing_slots == []
    assert coverage.reserve_complete is False


def test_reserve_matching_uses_a_disjoint_second_set() -> None:
    values = [
        _with_hours(f"restaurant:all:{index}", "07:00-21:00") for index in range(18)
    ]

    coverage = _coverage(values, days=3)

    hard_ids = {item.restaurant_id for item in coverage.hard_assignments}
    reserve_ids = {item.restaurant_id for item in coverage.reserve_assignments}
    assert coverage.hard_complete is True
    assert coverage.reserve_complete is True
    assert len(hard_ids) == 9
    assert len(reserve_ids) == 9
    assert hard_ids.isdisjoint(reserve_ids)
