import pytest
from pydantic import ValidationError

from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.tests.factories import candidate, food, payload


def test_camel_case_input_round_trips_with_aliases() -> None:
    raw = payload(
        days=3,
        places=[candidate("ho_guom", priority="user_input")],
        foods=[food()],
    )

    parsed = ItineraryPlannerInput.model_validate(raw)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert parsed.trip.start_date.isoformat() == "2026-08-20"
    assert parsed.trip.budget.currency == "VND"
    assert parsed.food[0].supported_meals[0].value == "breakfast"
    assert dumped["trip"]["startDate"] == "2026-08-20"
    assert dumped["places"][0]["durationMinutes"] == 60
    assert "openingHours" in dumped["places"][0]
    assert dumped["places"][0]["sourceKind"] == "generic"
    assert dumped["places"][0]["offeredActivityIds"] == []
    assert dumped["places"][0]["timeSource"] == "unknown"


def test_accepts_estimated_budget_metadata_from_place_checker() -> None:
    raw = payload()
    raw["trip"]["budget"] = {
        "amount": 2_252_556,
        "currency": "VND",
        "source": "estimated_daily_cost",
        "dailyEstimate": {
            "accommodation": 329_272,
            "food": 150_000,
            "localTransport": 171_580,
            "activities": 100_000,
            "total": 750_852,
        },
        "profileVersion": "hanoi-test-v1",
    }

    parsed = ItineraryPlannerInput.model_validate(raw)

    assert parsed.trip.budget.amount == 2_252_556
    assert parsed.trip.budget.source == "estimated_daily_cost"
    assert parsed.trip.budget.daily_estimate is not None
    assert parsed.trip.budget.daily_estimate.total == 750_852


def test_rejects_duplicate_ids_across_places_and_food() -> None:
    raw = payload(places=[candidate("duplicate")], foods=[food("duplicate")])

    with pytest.raises(ValidationError, match="placeId must be unique"):
        ItineraryPlannerInput.model_validate(raw)


def test_candidate_price_cost_is_required() -> None:
    place = candidate("missing_price")
    del place["price"]["cost"]

    with pytest.raises(ValidationError) as error:
        ItineraryPlannerInput.model_validate(payload(places=[place]))

    assert error.value.errors()[0]["loc"] == ("places", 0, "price", "cost")


@pytest.mark.parametrize(
    ("field", "value"),
    [("durationMinutes", 0), ("rating", 5.1), ("reviewCount", -1)],
)
def test_rejects_invalid_candidate_values(field: str, value: object) -> None:
    place = candidate("invalid")
    place[field] = value

    with pytest.raises(ValidationError):
        ItineraryPlannerInput.model_validate(payload(places=[place]))


def test_rejects_opening_day_outside_trip() -> None:
    place = candidate(
        "invalid_day",
        opening_hours={"2": [{"startMinute": 480, "endMinute": 600}]},
    )

    with pytest.raises(ValidationError, match="canonical trip day numbers"):
        ItineraryPlannerInput.model_validate(payload(days=1, places=[place]))
