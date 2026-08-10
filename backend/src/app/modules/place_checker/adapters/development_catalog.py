from hashlib import sha256

from app.shared.contracts.place import Coordinates, PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent


class DevelopmentCatalog:
    """Deterministic local adapter used only until a real place provider is wired."""

    @staticmethod
    def _coordinates(seed: str, index: int = 0) -> Coordinates:
        digest = sha256(f"{seed}:{index}".encode()).digest()
        latitude = 10.0 + int.from_bytes(digest[:2], "big") / 65535 * 12
        longitude = 102.0 + int.from_bytes(digest[2:4], "big") / 65535 * 8
        return Coordinates(latitude=latitude, longitude=longitude)

    async def resolve(
        self,
        candidate: PlaceCandidate,
        intent: TripIntent,
    ) -> VerifiedPlace | None:
        coordinates = candidate.coordinates or self._coordinates(
            f"{intent.destination}:{candidate.name}"
        )
        return VerifiedPlace(
            place_id=f"dev-{sha256(candidate.name.encode()).hexdigest()[:12]}",
            name=candidate.name,
            coordinates=coordinates,
            source=candidate.source,
            verified=candidate.coordinates is not None,
            tags=candidate.tags,
        )

    async def discover(
        self,
        intent: TripIntent,
        limit: int,
    ) -> list[VerifiedPlace]:
        return [
            VerifiedPlace(
                place_id=f"dev-suggestion-{index + 1}",
                name=f"{intent.destination} suggestion {index + 1}",
                coordinates=self._coordinates(intent.destination, index),
                source="development_catalog",
                verified=False,
                tags=["suggestion"],
            )
            for index in range(limit)
        ]

