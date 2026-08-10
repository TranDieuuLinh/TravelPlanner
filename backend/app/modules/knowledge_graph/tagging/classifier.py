"""Conservative deterministic rules for the controlled place-tag vocabulary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.modules.knowledge_graph.text import normalize_knowledge_text


CLASSIFIER_SOURCE = "classifier:place-tags:v1"


@dataclass(frozen=True)
class TagEvidence:
    tag: str
    status: str
    confidence: float
    source: str
    evidence_summary: str


STRUCTURED_MARKERS: dict[str, tuple[str, ...]] = {
    "coffee": ("cafe", "coffee shop", "coffee store"),
    "bar": ("bar", "pub", "night club", "nightclub"),
    "cocktail": ("cocktail bar", "mixology"),
    "beer": ("beer", "brewery", "brewpub", "taproom"),
    "alcohol": ("bar", "pub", "night club", "nightclub", "brewery", "wine bar", "cocktail bar"),
    "karaoke": ("karaoke",),
    "spa": ("spa", "wellness center"),
    "massage": ("massage", "massage spa"),
    "market": ("market", "night market", "farmers market"),
    "shopping": ("market", "shopping mall", "shopping center"),
    "performance": ("theater", "theatre", "performing arts", "opera house"),
    "live_music": ("live music venue", "music venue", "jazz club"),
    "jazz": ("jazz club",),
    "rooftop": ("rooftop", "sky bar"),
    "street_food": ("street food", "food court"),
    "guided_tour": ("tour operator", "sightseeing tour", "tour agency"),
    "outdoor": ("park", "garden", "lake", "bridge", "outdoor attraction"),
    "indoor": ("museum", "theater", "theatre", "cinema", "spa", "massage", "karaoke"),
}

NAME_MARKERS: dict[str, tuple[str, ...]] = {
    "coffee": ("coffee", "cafe", "ca phe"),
    "cocktail": ("cocktail", "mixology"),
    "beer": ("beer", "bia hoi", "brewery", "taproom"),
    "karaoke": ("karaoke",),
    "spa": ("spa", "wellness"),
    "massage": ("massage",),
    "market": ("market", "cho dem", "cho dia phuong"),
    "rooftop": ("rooftop", "sky bar", "sky lounge"),
    "live_music": ("live music", "music venue"),
    "acoustic": ("acoustic",),
    "jazz": ("jazz",),
    "performance": ("theater", "theatre", "opera house"),
    "guided_tour": ("guided tour", "sightseeing tour", "night tour"),
    "romantic": ("romantic",),
    "local": ("local market", "cho dia phuong"),
    "street_food": ("street food",),
}


def _json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, ValueError):
        return fallback


def _contains(value: str, marker: str) -> bool:
    normalized = f" {normalize_knowledge_text(value)} "
    target = f" {normalize_knowledge_text(marker)} "
    return target in normalized


def _structured_labels(properties: dict[str, str]) -> list[str]:
    metadata = _json(properties.get("metadata"), {})
    google = metadata.get("google") if isinstance(metadata, dict) else None
    labels = [
        properties.get("place_type", ""),
        properties.get("place_category", ""),
        properties.get("source_category", ""),
        properties.get("beverage_category", ""),
        properties.get("cuisine", ""),
    ]
    if isinstance(google, dict):
        labels.append(str(google.get("category") or ""))
        labels.extend(
            str(value) for value in google.get("types", []) if isinstance(value, str)
        )
    return [label for label in labels if label]


def _property_source(
    property_sources: dict[str, str | None],
    *keys: str,
) -> str:
    return next(
        (
            source
            for key in keys
            if (source := property_sources.get(key))
        ),
        CLASSIFIER_SOURCE,
    )


def _late_night(properties: dict[str, str]) -> bool:
    rows = _json(properties.get("opening_hours"), [])
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_slots = str(
            row.get("rawTimeSlots") or row.get("raw_time_slots") or ""
        ).replace("\u202f", " ").replace("\xa0", " ")
        if "open 24 hours" in raw_slots.casefold() or row.get("is24Hours") is True:
            return True
        for raw_slot in raw_slots.split(","):
            clock_values = re.findall(
                r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)",
                raw_slot,
                flags=re.IGNORECASE,
            )
            if not clock_values:
                continue
            hour_text, minute_text, meridiem = clock_values[-1]
            hour = int(hour_text) % 12
            if meridiem.casefold() == "pm":
                hour += 12
            minute = int(minute_text or 0)
            closing_minutes = hour * 60 + minute
            if closing_minutes >= 22 * 60 or closing_minutes < 4 * 60:
                return True
        end = str(row.get("end") or "")
        if end >= "22:00" or end in {"00:00", "24:00"}:
            return True
        slots = row.get("timeSlots") or row.get("time_slots") or []
        if isinstance(slots, list) and any(
            isinstance(slot, dict) and str(slot.get("end") or "") >= "22:00"
            for slot in slots
        ):
            return True
    return False


def _verified_free(properties: dict[str, str]) -> bool:
    admission = _json(properties.get("admission_price"), {})
    return bool(
        isinstance(admission, dict)
        and admission.get("status") == "verified_free"
        and admission.get("representativeAmount") in {0, 0.0, "0"}
    )


def classify_place(
    *,
    name: str,
    properties: dict[str, str],
    property_sources: dict[str, str | None],
) -> list[TagEvidence]:
    """Return only evidence-supported effective tags for one Place entity."""
    candidates: dict[str, TagEvidence] = {}

    def add(evidence: TagEvidence) -> None:
        current = candidates.get(evidence.tag)
        if current is None or evidence.confidence > current.confidence:
            candidates[evidence.tag] = evidence

    structured = _structured_labels(properties)
    for tag, markers in STRUCTURED_MARKERS.items():
        match = next(
            (
                (label, marker)
                for label in structured
                for marker in markers
                if _contains(label, marker)
            ),
            None,
        )
        if match is None:
            continue
        label, marker = match
        add(
            TagEvidence(
                tag=tag,
                status="source_backed",
                confidence=0.95,
                source=_property_source(
                    property_sources,
                    "source_category",
                    "place_type",
                    "metadata",
                ),
                evidence_summary=f"Structured category '{label}' matched '{marker}'.",
            )
        )

    for tag, markers in NAME_MARKERS.items():
        marker = next((marker for marker in markers if _contains(name, marker)), None)
        if marker:
            add(
                TagEvidence(
                    tag=tag,
                    status="inferred",
                    confidence=0.80,
                    source=CLASSIFIER_SOURCE,
                    evidence_summary=f"Canonical name matched controlled marker '{marker}'.",
                )
            )

    current_tags = set(candidates)
    if current_tags.intersection({"spa", "massage", "karaoke", "performance"}):
        add(TagEvidence("indoor", "inferred", 0.85, CLASSIFIER_SOURCE, "Activity type normally takes place indoors."))
    if current_tags.intersection({"bar", "cocktail", "beer", "alcohol"}):
        add(TagEvidence("adult_optional", "inferred", 0.80, CLASSIFIER_SOURCE, "Alcohol-oriented venue category."))
    if current_tags.intersection({"karaoke"}):
        add(TagEvidence("group_friendly", "inferred", 0.85, CLASSIFIER_SOURCE, "Karaoke is normally a group activity."))
        add(TagEvidence("lively", "inferred", 0.80, CLASSIFIER_SOURCE, "Karaoke is normally a lively activity."))
    if current_tags.intersection({"rooftop"}):
        add(TagEvidence("night_view", "inferred", 0.80, CLASSIFIER_SOURCE, "Rooftop or sky venue provides an elevated-view signal."))
        add(TagEvidence("weather_sensitive", "inferred", 0.85, CLASSIFIER_SOURCE, "Rooftop experience may be affected by weather."))
    if current_tags.intersection({"outdoor"}):
        add(TagEvidence("weather_sensitive", "inferred", 0.85, CLASSIFIER_SOURCE, "Outdoor setting may be affected by weather."))
    if current_tags.intersection({"market"}):
        add(TagEvidence("shopping", "inferred", 0.85, CLASSIFIER_SOURCE, "Market identity supports shopping activity."))
        add(TagEvidence("lively", "inferred", 0.72, CLASSIFIER_SOURCE, "Market identity weakly supports a lively setting."))
    if current_tags.intersection({"live_music", "performance"}):
        add(TagEvidence("reservation_recommended", "inferred", 0.72, CLASSIFIER_SOURCE, "Scheduled performance may benefit from advance confirmation."))
    if _late_night(properties):
        add(
            TagEvidence(
                "late_night",
                "source_backed",
                0.95,
                _property_source(property_sources, "opening_hours"),
                "Stored opening-hours snapshot contains a closing time at or after 22:00.",
            )
        )
    if _verified_free(properties):
        add(
            TagEvidence(
                "free",
                "verified",
                0.99,
                _property_source(property_sources, "admission_price"),
                "Verified admission-price property records zero standard admission.",
            )
        )

    return sorted(candidates.values(), key=lambda item: item.tag)
