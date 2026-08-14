from app.modules.itinerary_planner.tests.factories import candidate
from app.modules.itinerary_planner.tests.optimizer_fixtures import (
    base_payload,
    solve_payload,
)


def source_candidate(place_id: str, source: str, window: tuple[int, int]) -> dict:
    value = candidate(
        place_id,
        priority="user_input",
        duration_minutes=30,
        opening_hours={
            "1": [{"startMinute": window[0], "endMinute": window[1]}]
        },
    )
    value["sourceKind"] = source
    return value


def test_source_mix_hits_rounded_morning_and_evening_targets() -> None:
    places = [
        source_candidate("morning_special", "special_experience", (540, 720)),
        source_candidate("morning_offer", "offer_item", (540, 720)),
        source_candidate("evening_special_a", "special_experience", (1080, 1380)),
        source_candidate("evening_special_b", "special_experience", (1080, 1380)),
        source_candidate("evening_offer", "offer_item", (1080, 1380)),
    ]

    result, _, _ = solve_payload(base_payload(places=places))
    periods = {item.period: item for item in result.source_mix}

    assert result.objective_components["sourceMixDeviationCost"] == 0
    assert (periods["morning"].target_special, periods["morning"].target_offer) == (1, 1)
    assert (periods["morning"].actual_special, periods["morning"].actual_offer) == (1, 1)
    assert (periods["evening"].target_special, periods["evening"].target_offer) == (2, 1)
    assert (periods["evening"].actual_special, periods["evening"].actual_offer) == (2, 1)
    assert not periods["morning"].fallback_used
    assert not periods["evening"].fallback_used


def test_offer_fills_shortage_in_same_period_and_records_fallback() -> None:
    places = [
        source_candidate("morning_offer_a", "offer_item", (540, 720)),
        source_candidate("morning_offer_b", "offer_item", (540, 720)),
    ]

    result, _, _ = solve_payload(base_payload(places=places))
    morning = next(item for item in result.source_mix if item.period == "morning")

    assert (morning.target_special, morning.target_offer) == (1, 1)
    assert (morning.actual_special, morning.actual_offer) == (0, 2)
    assert morning.fallback_used
    assert result.objective_components["sourceMixDeviationCost"] == 0


def test_both_source_is_assigned_once_for_the_period() -> None:
    places = [
        source_candidate("morning_both", "both", (540, 720)),
        source_candidate("morning_offer", "offer_item", (540, 720)),
    ]

    result, _, _ = solve_payload(base_payload(places=places))
    morning = next(item for item in result.source_mix if item.period == "morning")

    assert morning.actual_special + morning.actual_offer == 2
    assert (morning.actual_special, morning.actual_offer) == (1, 1)
    assert not morning.fallback_used
