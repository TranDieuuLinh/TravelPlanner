from __future__ import annotations

import re
import unicodedata

from app.modules.plans.explorer.schema import (
    PlaceCandidateSourceType,
    UnifiedPlaceCandidate,
)


_URL_NAME_NOISE = re.compile(
    r"\b(?:"
    r"don['’]?t skip|do not skip|for our|find video info|link in bio|"
    r"comment ['\"]?link|recommendations? for|tap the|check out|send us|"
    r"more recommendations|travel guide"
    r")\b",
    flags=re.IGNORECASE,
)
_LIST_MARKERS = ("📌", "📍", "🚂", "🧑‍🍳", "•", "→")


def is_credible_url_candidate(candidate: UnifiedPlaceCandidate) -> bool:
    """Reject URL captions/lists that were mistaken for one place name."""
    if not _is_url_only(candidate):
        return True

    name = re.sub(r"\s+", " ", candidate.name).strip()
    words = name.split()
    if not name or len(name) > 80 or len(words) > 10:
        return False
    if _URL_NAME_NOISE.search(name):
        return False
    if sum(name.count(marker) for marker in _LIST_MARKERS) > 1:
        return False
    if name.count("#") > 1 or name.count("|") > 1:
        return False
    return True


def is_schedulable_place(
    *,
    is_url_source: bool,
    resolution_status: str,
    latitude: object | None,
    longitude: object | None,
    resolved_name: str,
    city: str | None,
    destination: str | None,
    country: str | None,
) -> bool:
    """Only verified, specifically identified URL places may enter a plan."""
    if latitude is None or longitude is None:
        return False
    if not is_url_source:
        return resolution_status in {"resolved", "provisional"}
    if resolution_status != "resolved":
        return False

    resolved_key = _slug(resolved_name)
    broad_location_keys = {
        _slug(value)
        for value in (city, destination, country)
        if value
    }
    return bool(resolved_key and resolved_key not in broad_location_keys)


def has_url_source(candidate: UnifiedPlaceCandidate) -> bool:
    return any(
        source.type is PlaceCandidateSourceType.url and source.url
        for source in candidate.sources
    )


def concise_source_activity(value: str | None, *, limit: int = 140) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text or _URL_NAME_NOISE.search(text):
        return None
    if len(text) <= limit:
        return text

    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0].strip()
    if first_sentence and len(first_sentence) <= limit:
        return first_sentence
    return None


def _is_url_only(candidate: UnifiedPlaceCandidate) -> bool:
    source_types = {source.type for source in candidate.sources}
    return bool(source_types) and source_types == {PlaceCandidateSourceType.url}


def _slug(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "-", without_marks).strip("-")
