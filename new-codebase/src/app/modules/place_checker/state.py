from typing import TypedDict

from app.modules.place_checker.contract import PlaceCheckerOutput
from app.shared.contracts.place import PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent


class PlaceCheckerState(TypedDict, total=False):
    intent: TripIntent
    candidates: list[PlaceCandidate]
    resolved_places: list[VerifiedPlace]
    rejected_candidates: list[PlaceCandidate]
    output: PlaceCheckerOutput

