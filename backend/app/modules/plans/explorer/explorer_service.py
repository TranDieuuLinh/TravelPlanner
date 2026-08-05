import re
import unicodedata

from app.modules.plans.domain.entities import TravelIntent
from app.modules.plans.explorer.preference_parser import PreferenceParser
from app.modules.plans.explorer.question_builder import ExplorerQuestionBuilder
from app.modules.plans.explorer.schema import (
    ExplorerContextResponse,
    FullExploreRequest,
    IntakeInputCompleteness,
    MissingFieldInfo,
)
from app.modules.plans.schema import ExplorerRequest


_VAGUE_REQUEST_PATTERNS = (
    r"^(?:toi )?muon di du lich(?: di)?$",
    r"^di du lich(?: di)?$",
    r"^(?:hay )?(?:tao|lap) (?:mot )?(?:ke hoach|lich trinh) du lich$",
    r"^i (?:just )?want to travel$",
    r"^(?:please )?(?:plan )?(?:a )?trip(?: for me)?$",
    r"^(?:take|send) me somewhere$",
    r"^surprise me$",
)

class ExplorerService:
    def __init__(
        self,
        parser: PreferenceParser | None = None,
        question_builder: ExplorerQuestionBuilder | None = None,
    ) -> None:
        self.parser = parser or PreferenceParser()
        self.question_builder = question_builder or ExplorerQuestionBuilder()

    def explore(self, payload: ExplorerRequest) -> TravelIntent:
        return TravelIntent(
            destination=payload.destination.strip(),
            days=payload.days,
            budget=payload.budget,
            travelStyle=payload.travel_style.strip(),
            pace=payload.pace,
            interests=self.parser.normalize(payload.interests),
            mustVisitPlaces=[place.strip() for place in payload.must_visit_places if place.strip()],
            avoidPlaces=[place.strip() for place in payload.avoid_places if place.strip()],
            constraints=[constraint.strip() for constraint in payload.constraints if constraint.strip()],
            clarifyingQuestions=self.question_builder.build(payload),
        )


def apply_raw_prompt_completeness(
    payload: FullExploreRequest,
    explorer: ExplorerContextResponse,
) -> ExplorerContextResponse:
    """Attach V2 completeness metadata only for plain raw-prompt intake.

    URL, OCR/image, and pre-built candidate flows intentionally retain their
    existing Explorer behavior.
    """

    if payload.urls or payload.image_contexts or payload.place_candidates:
        return explorer

    normalized_request = _normalize_text(payload.raw_request)
    destination = payload.destination.strip()
    normalized_destination = _normalize_text(destination)
    normalized_intent_destination = _normalize_text(
        explorer.intent.destination
    )
    destination_was_provided = (
        not _is_vague_request(normalized_request)
        and (
            bool(
                normalized_destination
                and normalized_destination != "unspecified"
            )
            or bool(
                normalized_intent_destination
                and normalized_intent_destination != "unspecified"
                and normalized_intent_destination in normalized_request
            )
        )
    )
    # Destination is the only blocking field. Duration, party, budget and the
    # remaining TripIntent fields already have domain defaults and must not
    # force another conversational round-trip.
    provided = {"destination": destination_was_provided}
    missing_fields = [
        MissingFieldInfo(field=field)
        for field, was_provided in provided.items()
        if not was_provided
    ]
    if not destination_was_provided:
        completeness = IntakeInputCompleteness.vague
        mode = "vague"
    elif missing_fields:
        completeness = IntakeInputCompleteness.partial
        mode = "partial"
    else:
        completeness = IntakeInputCompleteness.complete
        mode = "confirmed"

    intent_updates: dict[str, object] = {"clarifying_questions": []}
    if not destination_was_provided:
        # Do not turn a destination invented by the formatter into user input.
        intent_updates["destination"] = ""
    trip_intent_updates: dict[str, object] = {
        "clarifying_questions": intent_updates["clarifying_questions"]
    }
    if "destination" in intent_updates:
        trip_intent_updates["destination"] = intent_updates["destination"]
    trip_intent = explorer.trip_intent.model_copy(
        update=trip_intent_updates
    )
    return explorer.model_copy(
        update={
            "mode": mode,
            "trip_intent": trip_intent,
            "input_completeness": completeness,
            "missing_fields": missing_fields,
            "assumptions": [],
            "missing_info_questions": [],
            "trace": {
                **explorer.trace,
                "inputSource": "raw_prompt",
            },
        }
    )


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _is_vague_request(normalized_request: str) -> bool:
    return not normalized_request or any(
        re.fullmatch(pattern, normalized_request)
        for pattern in _VAGUE_REQUEST_PATTERNS
    )
