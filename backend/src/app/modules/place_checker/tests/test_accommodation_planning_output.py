from types import SimpleNamespace

from app.modules.place_checker.accommodation_planning_output import (
    select_accommodations,
)
from app.modules.place_checker.enums import CostTier, VerificationStatus
from app.shared.contracts.place import Coordinates


def _checked_hotel(place_id: str, latitude: float, cost: int):
    return SimpleNamespace(
        place_id=place_id,
        canonical_name=place_id,
        category="accommodation",
        coordinates=Coordinates(latitude=latitude, longitude=105.85),
        address=None,
        rating=4.5,
        review_count=100,
        evaluation=SimpleNamespace(avoid_conflicts=[]),
        verification=SimpleNamespace(status=VerificationStatus.verified_kg),
        cost=SimpleNamespace(
            currency="VND",
            minimum=cost,
            typical=cost,
            maximum=cost,
            tier=CostTier.medium,
        ),
    )


def test_budget_pool_orders_nearest_accommodation_first() -> None:
    result = SimpleNamespace(
        trip_context=SimpleNamespace(
            budget=SimpleNamespace(currency="VND", level="medium")
        ),
        checked_places=[
            _checked_hotel("hotel:outside-low", 23.03, 100_000),
            _checked_hotel("hotel:near", 21.03, 200_000),
            _checked_hotel("hotel:target-price-far", 22.03, 300_000),
            _checked_hotel("hotel:middle", 21.13, 400_000),
            _checked_hotel("hotel:outside-high", 23.53, 500_000),
        ],
    )

    selected = select_accommodations(
        result,
        anchor_coordinates=[Coordinates(latitude=21.03, longitude=105.85)],
    )

    assert [item.place_id for item in selected] == [
        "hotel:near",
        "hotel:middle",
        "hotel:target-price-far",
    ]
