from typing import Protocol

from app.shared.contracts.place import VerifiedPlace


class RoutingProvider(Protocol):
    async def travel_minutes(
        self,
        origin: VerifiedPlace,
        destination: VerifiedPlace,
    ) -> int: ...


class EstimatedRoutingProvider:
    async def travel_minutes(
        self,
        origin: VerifiedPlace,
        destination: VerifiedPlace,
    ) -> int:
        lat_delta = abs(
            origin.coordinates.latitude - destination.coordinates.latitude
        )
        lon_delta = abs(
            origin.coordinates.longitude - destination.coordinates.longitude
        )
        return max(10, min(120, round((lat_delta + lon_delta) * 35)))

