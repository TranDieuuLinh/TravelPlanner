from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from math import ceil
from typing import Protocol


class TransportCostEstimator(Protocol):
    def estimate(
        self,
        distance_meters: int,
        profile: str,
        people: int,
    ) -> tuple[int, int]:
        """Return daytime cost and late-night surcharge, both per person."""
        ...


@dataclass(frozen=True, slots=True)
class LocalTransportCostEstimate:
    distance_meters: int
    people: int
    vehicle_count: int
    daytime_cost_per_person: int
    late_night_surcharge_per_person: int
    currency: str
    provider: str
    market: str
    policy_version: str
    source_url: str
    verified_on: str

    @property
    def maximum_cost_per_person(self) -> int:
        return self.daytime_cost_per_person + self.late_night_surcharge_per_person


@dataclass(frozen=True, slots=True)
class XanhSmTransportCostEstimator:
    """Conservative per-person estimate from Green SM Car's Hanoi public fare."""

    opening_distance_meters: int = 2_000
    opening_fare: int = 30_500
    rate_to_12_km: int = 14_700
    rate_to_25_km: int = 13_800
    rate_after_25_km: int = 11_900
    late_night_surcharge_per_vehicle: int = 20_000
    planning_buffer_percent: int = 15
    vehicle_capacity: int = 4
    currency: str = "VND"
    provider: str = "green_sm_car"
    market: str = "VN-HN"
    policy_version: str = "green-sm-car-hanoi-public-v1"
    source_url: str = (
        "https://www.greensm.com/vn-vi/news/bang-gia-xe-taxi-ha-noi"
    )
    verified_on: str = "2026-08-14"

    def estimate(
        self,
        distance_meters: int,
        profile: str,
        people: int,
    ) -> tuple[int, int]:
        estimate = self.estimate_breakdown(distance_meters, profile, people)
        return (
            estimate.daytime_cost_per_person,
            estimate.late_night_surcharge_per_person,
        )

    def estimate_breakdown(
        self,
        distance_meters: int,
        profile: str,
        people: int,
    ) -> LocalTransportCostEstimate:
        if profile != "auto":
            raise ValueError("Xanh SM Car pricing only supports the auto profile")
        if distance_meters < 0:
            raise ValueError("distance_meters cannot be negative")
        if people < 1:
            raise ValueError("people must be positive")

        vehicle_count = ceil(people / self.vehicle_capacity)
        if distance_meters == 0:
            daytime_per_person = 0
            night_per_person = 0
        else:
            vehicle_fare = self._vehicle_fare(distance_meters)
            buffered_vehicle_fare = self._ceil_decimal(
                Decimal(vehicle_fare)
                * (Decimal(100 + self.planning_buffer_percent) / Decimal(100))
            )
            daytime_per_person = ceil(
                buffered_vehicle_fare * vehicle_count / people
            )
            night_per_person = ceil(
                self.late_night_surcharge_per_vehicle * vehicle_count / people
            )

        return LocalTransportCostEstimate(
            distance_meters=distance_meters,
            people=people,
            vehicle_count=vehicle_count,
            daytime_cost_per_person=daytime_per_person,
            late_night_surcharge_per_person=night_per_person,
            currency=self.currency,
            provider=self.provider,
            market=self.market,
            policy_version=self.policy_version,
            source_url=self.source_url,
            verified_on=self.verified_on,
        )

    def _vehicle_fare(self, distance_meters: int) -> int:
        if distance_meters <= self.opening_distance_meters:
            return self.opening_fare

        fare = Decimal(self.opening_fare)
        remaining = distance_meters - self.opening_distance_meters
        first_tier = min(remaining, 10_000)
        fare += Decimal(first_tier) / 1000 * self.rate_to_12_km
        remaining -= first_tier

        second_tier = min(remaining, 13_000)
        fare += Decimal(second_tier) / 1000 * self.rate_to_25_km
        remaining -= second_tier

        if remaining > 0:
            fare += Decimal(remaining) / 1000 * self.rate_after_25_km
        return self._ceil_decimal(fare)

    @staticmethod
    def _ceil_decimal(value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_CEILING))
