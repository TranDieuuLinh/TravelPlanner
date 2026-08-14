from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DailyCostEstimate:
    """Per-person daily cost components in a single currency."""

    accommodation: int
    food: int
    local_transport: int
    activities: int
    misc: int
    currency: str

    def __post_init__(self) -> None:
        amounts = (
            self.accommodation,
            self.food,
            self.local_transport,
            self.activities,
            self.misc,
        )
        if any(amount < 0 for amount in amounts):
            raise ValueError("daily cost components cannot be negative")
        if len(self.currency.strip()) != 3:
            raise ValueError("currency must be a three-letter code")

    @property
    def total(self) -> int:
        return (
            self.accommodation
            + self.food
            + self.local_transport
            + self.activities
            + self.misc
        )


class DailyCostCalculator:
    @staticmethod
    def estimate(
        *,
        accommodation: int = 0,
        food: int = 0,
        local_transport: int = 0,
        activities: int = 0,
        misc: int = 0,
        currency: str = "VND",
    ) -> DailyCostEstimate:
        return DailyCostEstimate(
            accommodation=accommodation,
            food=food,
            local_transport=local_transport,
            activities=activities,
            misc=misc,
            currency=currency.upper(),
        )
