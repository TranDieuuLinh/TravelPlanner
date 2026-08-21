import pytest
from pydantic import ValidationError

from app.modules.itinerary_planner.contract import ItineraryPlannerInput
from app.modules.itinerary_planner.tests.factories import (
    candidate,
    entertainment,
    food,
    payload,
)


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
    assert parsed.food[0].venue_type.value == "restaurant"
    assert parsed.trip.party is not None
    assert parsed.trip.party.kids == 0
    assert dumped["trip"]["startDate"] == "2026-08-20"
    assert dumped["places"][0]["durationMinutes"] == 60
    assert "openingHours" in dumped["places"][0]
    assert dumped["places"][0]["sourceKind"] == "generic"
    assert dumped["places"][0]["offeredActivityIds"] == []
    assert dumped["places"][0]["timeSource"] == "unknown"
    assert dumped["food"][0]["venueType"] == "restaurant"
    assert dumped["trip"]["preferences"]["tags"] == [
        "Culture",
        "local experience",
    ]


def test_entertainment_pool_is_nullable_and_round_trips_separately() -> None:
    parsed = ItineraryPlannerInput.model_validate(payload())
    assert parsed.entertainment is None

    parsed = ItineraryPlannerInput.model_validate(
        payload(
            entertainment_items=[entertainment("cafe", entity_type="drink_dessert")]
        )
    )
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert parsed.entertainment is not None
    assert parsed.entertainment[0].entity_type == "drink_dessert"
    assert dumped["entertainment"][0]["entityType"] == "drink_dessert"


def test_accepts_legacy_preference_list_and_rejects_invalid_audience() -> None:
    raw = payload(places=[candidate("legacy")])
    raw["trip"].pop("party")
    raw["trip"]["preferences"] = ["history"]

    parsed = ItineraryPlannerInput.model_validate(raw)

    assert parsed.trip.party is not None
    assert parsed.trip.party.adults == parsed.trip.people
    assert parsed.trip.preferences.tags == ["history"]

    raw["places"][0]["audience"] = {
        "adultOnly": True,
        "kidSuitable": True,
    }
    with pytest.raises(ValidationError, match="adult-only"):
        ItineraryPlannerInput.model_validate(raw)


def test_food_venue_type_round_trips_and_rejects_unknown_values() -> None:
    drink = food(venue_type="drink_dessert")
    parsed = ItineraryPlannerInput.model_validate(payload(foods=[drink]))

    assert parsed.food[0].venue_type.value == "drink_dessert"
    assert (
        parsed.model_dump(mode="json", by_alias=True)["food"][0]["venueType"]
        == "drink_dessert"
    )

    drink["venueType"] = "dessert_restaurant"
    with pytest.raises(ValidationError):
        ItineraryPlannerInput.model_validate(payload(foods=[drink]))


def test_accepts_place_checker_unique_meal_matching_feasibility() -> None:
    raw = payload(days=2)
    raw["foodCoverage"] = {
        "days": 2,
        "hardComplete": True,
        "reserveComplete": False,
        "hardAssignments": [
            {"day": 1, "meal": "breakfast", "restaurantId": "food:breakfast"}
        ],
        "hardMissingSlots": [],
        "reserveAssignments": [],
        "reserveMissingSlots": [
            {"day": 2, "meal": "dinner"},
        ],
    }

    parsed = ItineraryPlannerInput.model_validate(raw)
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert parsed.food_coverage.days == 2
    assert parsed.food_coverage.hard_assignments[0].restaurant_id == ("food:breakfast")
    assert dumped["foodCoverage"]["reserveMissingSlots"] == [
        {"day": 2, "meal": "dinner"}
    ]


def test_rejects_food_coverage_for_a_different_trip_length() -> None:
    raw = payload(days=2)
    raw["foodCoverage"] = {"days": 3}

    with pytest.raises(ValidationError, match="foodCoverage days must match"):
        ItineraryPlannerInput.model_validate(raw)


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


def test_candidate_accepts_structured_source_note() -> None:
    place = candidate("source_note")
    place["notes"] = {
        "text": "Đến trước 8 giờ",
        "sourceType": "url",
        "sourceUrl": "https://example.test/video",
    }
    place["personalNotes"] = "Người dùng muốn ghé sau bữa sáng."

    parsed = ItineraryPlannerInput.model_validate(payload(places=[place]))
    dumped = parsed.model_dump(mode="json", by_alias=True)

    assert parsed.places[0].notes is not None
    assert parsed.places[0].notes.source_type == "url"
    assert dumped["places"][0]["notes"] == place["notes"]
    assert dumped["places"][0]["personalNotes"] == place["personalNotes"]


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
