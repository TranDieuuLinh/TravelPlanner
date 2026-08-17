from app.shared.contracts.trip import TripIntent


def test_trip_intent_defaults_to_three_days() -> None:
    intent = TripIntent(destination="Huế")

    assert intent.days == 3
