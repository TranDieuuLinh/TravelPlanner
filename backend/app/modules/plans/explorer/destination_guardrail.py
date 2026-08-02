from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.place_policy import has_url_source
from app.modules.plans.explorer.schema import (
    ExplorerContextResponse,
    UnifiedPlaceCandidate,
)
from app.shared.errors import AppError


@dataclass(frozen=True)
class SourceDestinationDecision:
    destination: str | None
    supporting_stop_count: int = 0
    total_located_stop_count: int = 0


def infer_url_destination_hint(
    candidates: list[UnifiedPlaceCandidate],
) -> SourceDestinationDecision:
    """Infer a conservative resolver hint from explicit URL search regions."""

    url_candidates = [
        candidate for candidate in candidates if has_url_source(candidate)
    ]
    regions = [
        candidate.search_region.strip()
        for candidate in url_candidates
        if candidate.search_region and candidate.search_region.strip()
    ]
    # A single region attached to one stop in a larger itinerary may only be a
    # day trip. Require at least half the URL stops to carry the same hint.
    decision = _dominant_destination(regions)
    if (
        decision.destination is not None
        and len(regions) < max(1, (len(url_candidates) + 1) // 2)
    ):
        return SourceDestinationDecision(None)
    return decision


def enforce_url_destination(
    explorer: ExplorerContextResponse,
    *,
    requested_destination: str,
    resolutions: list[PlaceResolution],
    extraction_hint: SourceDestinationDecision,
) -> ExplorerContextResponse:
    """Make evidenced URL geography authoritative over a conflicting prompt."""

    located_stops = [
        (
            resolution.candidate.search_region.strip()
            if resolution.candidate.search_region
            and resolution.candidate.search_region.strip()
            else (resolution.city or "").strip()
        )
        for resolution in resolutions
        if resolution.status == "resolved"
        and has_url_source(resolution.candidate)
    ]
    located_stops = [location for location in located_stops if location]
    decision = _dominant_destination(located_stops)
    if decision.destination is None:
        decision = extraction_hint
    if decision.destination is None:
        return explorer

    source_destination = decision.destination
    requested_key = _location_key(requested_destination)
    source_key = _location_key(source_destination)
    requested_matches = requested_key == source_key
    if (
        requested_key
        and requested_key != "unspecified"
        and not requested_matches
    ):
        raise AppError(
            409,
            "DESTINATION_CLARIFICATION_REQUIRED",
            (
                f"Reel này có các địa điểm ở {source_destination}, nhưng "
                f"chuyến đi hiện tại/yêu cầu của bạn là {requested_destination}. "
                f"Bạn muốn giữ {requested_destination} và chỉ dùng reel làm "
                f"tham khảo, tạo một chuyến {source_destination} riêng, hay "
                f"đổi chuyến đi hiện tại sang {source_destination}?"
            ),
            details={
                "requestedDestination": requested_destination,
                "sourceDestination": source_destination,
                "choices": [
                    "keep_prompt_destination",
                    "create_separate_reel_trip",
                    "follow_reel_destination",
                ],
            },
        )
    formatter_matches = (
        _location_key(explorer.intent.destination) == source_key
    )
    corrected = not formatter_matches
    trace = {
        **explorer.trace,
        "destinationGuardrail": {
            "status": "corrected" if corrected else "matched",
            "authority": "url_evidence",
            "requestedDestination": requested_destination,
            "sourceDestination": source_destination,
            "supportingStopCount": decision.supporting_stop_count,
            "locatedStopCount": decision.total_located_stop_count,
        },
    }
    assumptions = list(explorer.assumptions)
    if corrected:
        assumptions.append(
            "Destination was corrected to "
            f"{source_destination} because the formatter output conflicted "
            "with matching prompt and reel evidence."
        )
    return explorer.model_copy(
        update={
            "intent": explorer.intent.model_copy(
                update={"destination": source_destination}
            ),
            "assumptions": assumptions,
            "trace": trace,
        }
    )


def _dominant_destination(values: list[str]) -> SourceDestinationDecision:
    normalized = [
        (_location_key(value), value)
        for value in values
        if value.strip()
    ]
    normalized = [(key, value) for key, value in normalized if key]
    if not normalized:
        return SourceDestinationDecision(None)

    counts = Counter(key for key, _ in normalized)
    key, supporting_count = counts.most_common(1)[0]
    total_count = len(normalized)
    # One located stop is sufficient. With multiple cities, require a strong
    # majority so a day-trip region cannot silently replace the trip base.
    if total_count > 1 and (
        supporting_count < 2 or supporting_count / total_count < 0.75
    ):
        return SourceDestinationDecision(None)
    display_value = next(
        value
        for candidate_key, value in normalized
        if candidate_key == key
    )
    return SourceDestinationDecision(
        destination=display_value,
        supporting_stop_count=supporting_count,
        total_located_stop_count=total_count,
    )


def _location_key(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.strip().casefold())
    ascii_text = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", ascii_text)
        if token not in {"city", "province", "thanh", "pho", "tinh"}
    ]
    while tokens and tokens[-1] in {"vietnam", "viet", "nam", "vn"}:
        tokens.pop()
    return "-".join(tokens)
