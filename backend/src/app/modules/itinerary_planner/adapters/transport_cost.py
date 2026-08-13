from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from math import ceil


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
    policy_version: str = "green-sm-car-hanoi-public-v1"

    def estimate(
        self,
        distance_meters: int,
        profile: str,
        people: int,
    ) -> tuple[int, int]:
        if profile != "auto":
            raise ValueError("Xanh SM Car pricing only supports the auto profile")
        if distance_meters < 0:
            raise ValueError("distance_meters cannot be negative")
        if people < 1:
            raise ValueError("people must be positive")
        if distance_meters == 0:
            return 0, 0

        vehicle_fare = self._vehicle_fare(distance_meters)
        buffered_vehicle_fare = self._ceil_decimal(
            Decimal(vehicle_fare)
            * (Decimal(100 + self.planning_buffer_percent) / Decimal(100))
        )
        vehicle_count = ceil(people / self.vehicle_capacity)
        daytime_per_person = ceil(buffered_vehicle_fare * vehicle_count / people)
        night_per_person = ceil(
            self.late_night_surcharge_per_vehicle * vehicle_count / people
        )
        return daytime_per_person, night_per_person

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
