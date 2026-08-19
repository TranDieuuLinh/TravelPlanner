from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from math import ceil
from typing import Literal

from app.shared.tools.daily_cost import DailyCostCalculator, DailyCostEstimate
from app.shared.tools.transport_cost import (
    TransportCostEstimator,
    XanhSmTransportCostEstimator,
)

BudgetLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class DestinationDailyCostProfile:
    destination_keys: frozenset[str]
    currency: str
    accommodation_room_per_night: dict[BudgetLevel, int]
    meal_per_person: dict[BudgetLevel, int]
    activity_per_person: dict[BudgetLevel, int]
    activity_count: dict[BudgetLevel, int]
    transport_leg_count: dict[BudgetLevel, int]
    transport_distance_meters: int
    people_per_room: int
    meals_per_day: int
    version: str


@dataclass(frozen=True, slots=True)
class EstimatedTripBudget:
    daily_cost: DailyCostEstimate
    total_per_person: int
    days: int
    nights: int
    level: BudgetLevel
    profile_version: str


HANOI_DAILY_COST_PROFILE = DestinationDailyCostProfile(
    destination_keys=frozenset({"ha noi", "hanoi"}),
    currency="VND",
    # Positive-price KG percentiles observed on 2026-08-14.
    accommodation_room_per_night={
        "low": 658_544,
        "medium": 1_126_664,
        "high": 2_394_709,
    },
    meal_per_person={"low": 50_000, "medium": 150_000, "high": 300_000},
    activity_per_person={"low": 50_000, "medium": 50_000, "high": 425_000},
    activity_count={"low": 2, "medium": 3, "high": 4},
    transport_leg_count={"low": 4, "medium": 5, "high": 6},
    transport_distance_meters=5_000,
    people_per_room=2,
    meals_per_day=3,
    version="hanoi-kg-positive-price-percentiles-2026-08-14-v2",
)


class DestinationDailyBudgetEstimator:
    def __init__(
        self,
        transport_cost: TransportCostEstimator | None = None,
        profiles: tuple[DestinationDailyCostProfile, ...] = (
            HANOI_DAILY_COST_PROFILE,
        ),
    ) -> None:
        self.transport_cost = transport_cost or XanhSmTransportCostEstimator()
        self.profiles = profiles

    def estimate(
        self,
        *,
        destination: str,
        level: BudgetLevel,
        people: int,
        days: int,
    ) -> EstimatedTripBudget | None:
        if people < 1 or days < 1:
            raise ValueError("people and days must be positive")
        profile = self._profile(destination)
        if profile is None:
            return None

        rooms = ceil(people / profile.people_per_room)
        accommodation = ceil(
            profile.accommodation_room_per_night[level] * rooms / people
        )
        food = profile.meal_per_person[level] * profile.meals_per_day
        transport_per_leg, _ = self.transport_cost.estimate(
            profile.transport_distance_meters,
            "auto",
            people,
        )
        local_transport = transport_per_leg * profile.transport_leg_count[level]
        activities = (
            profile.activity_per_person[level] * profile.activity_count[level]
        )
        daily_cost = DailyCostCalculator.estimate(
            accommodation=accommodation,
            food=food,
            local_transport=local_transport,
            activities=activities,
            currency=profile.currency,
        )
        nights = max(0, days - 1)
        non_accommodation_daily = daily_cost.total - daily_cost.accommodation
        return EstimatedTripBudget(
            daily_cost=daily_cost,
            total_per_person=(
                non_accommodation_daily * days + accommodation * nights
            ),
            days=days,
            nights=nights,
            level=level,
            profile_version=profile.version,
        )

    def _profile(self, destination: str) -> DestinationDailyCostProfile | None:
        key = self._normalize(destination)
        return next(
            (profile for profile in self.profiles if key in profile.destination_keys),
            None,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        decomposed = unicodedata.normalize("NFKD", value)
        return " ".join(
            "".join(char for char in decomposed if not unicodedata.combining(char))
            .casefold()
            .split()
        )
