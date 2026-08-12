from app.modules.place_checker.contract import PlaceCheckerInput
from app.shared.contracts.place import PlaceCandidate
from app.shared.contracts.trip import TripIntent


class ExplorerInputProjector:
    @staticmethod
    def from_legacy(
        intent: TripIntent,
        candidates: list[PlaceCandidate],
    ) -> PlaceCheckerInput:
        return PlaceCheckerInput.model_validate(
            {
                "intent": intent.model_dump(),
                "candidates": [candidate.model_dump() for candidate in candidates],
            }
        )
