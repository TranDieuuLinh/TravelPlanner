from typing import Any, TypedDict

from app.modules.place_checker.contract import PlaceCheckerInput, PlaceCheckerOutput
from app.modules.place_checker.output_contract import PlaceCheckerResult
from app.shared.contracts.place import PlaceCandidate, VerifiedPlace
from app.shared.contracts.trip import TripIntent


class PlaceCheckerState(TypedDict, total=False):
    # Legacy compatibility graph state populated from Explorer.
    input_adm: str
    places: list[Any] | None
    input_items: list[Any] | None
    url_notes: list[Any] | None
    days: int
    budget: Any
    people: Any
    short_preferences: list[str]
    short_avoids: list[str]
    intent: TripIntent
    candidates: list[PlaceCandidate]
    resolved_places: list[VerifiedPlace]
    rejected_candidates: list[PlaceCandidate]
    output: PlaceCheckerOutput


class PlaceCheckerPipelineState(TypedDict, total=False):
    request_id: str
    correlation_id: str
    payload: PlaceCheckerInput | dict
    result: PlaceCheckerResult
