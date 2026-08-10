from typing import Protocol

from app.shared.contracts.place import PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent


class PlaceResolver(Protocol):
    async def resolve(
        self,
        candidate: PlaceCandidate,
        intent: TripIntent,
    ) -> VerifiedPlace | None: ...


class PlaceDiscovery(Protocol):
    async def discover(
        self,
        intent: TripIntent,
        limit: int,
    ) -> list[VerifiedPlace]: ...

