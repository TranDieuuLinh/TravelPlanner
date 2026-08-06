from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field


SOURCE_NOTE_MAX_LENGTH = 360
SOURCE_NOTE_PART_MAX_LENGTH = 180


class PlanNoteSource(BaseModel):
    """Provenance for the read-only source note stored in a plan snapshot."""

    type: str = Field(min_length=1, max_length=40)
    ref: str | None = Field(default=None, max_length=2048)
    evidence_types: list[str] = Field(
        default_factory=list,
        alias="evidenceTypes",
    )
    fetched_at: datetime | None = Field(default=None, alias="fetchedAt")

    model_config = {"populate_by_name": True}


def compose_plan_source_note(
    *,
    source_activity: str | None,
    source_evidence: dict[str, str] | None = None,
    provider_description: str | None = None,
) -> str | None:
    """Compose a compact display note from normalized, short evidence only."""

    evidence = source_evidence or {}
    ordered_values = [
        source_activity,
        *(evidence.get(key) for key in ("stt", "ocr", "caption", "metadata")),
        provider_description,
    ]
    parts: list[str] = []
    seen: set[str] = set()
    for value in ordered_values:
        part = _clean_note_part(value)
        if not part:
            continue
        key = _dedupe_key(part)
        if key in seen or any(key in existing or existing in key for existing in seen):
            continue
        seen.add(key)
        parts.append(part)

    if not parts:
        return None

    note = " ".join(parts)
    if len(note) <= SOURCE_NOTE_MAX_LENGTH:
        return note
    shortened = note[: SOURCE_NOTE_MAX_LENGTH + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened}…" if shortened else None


def source_note_provenance(
    *,
    source_refs: list[str],
    evidence_types: list[str],
    provider: str | None = None,
    provider_ref: str | None = None,
    provider_fetched_at: datetime | str | None = None,
    include_provider: bool = False,
) -> list[PlanNoteSource]:
    """Build stable note labels without storing another copy of note text."""

    normalized_evidence = list(dict.fromkeys(
        value.strip().casefold()
        for value in evidence_types
        if value and value.strip()
    ))
    sources: list[PlanNoteSource] = []
    for ref in dict.fromkeys(source_refs):
        if ref.startswith(("http://", "https://")):
            sources.append(
                PlanNoteSource(
                    type="url",
                    ref=ref,
                    evidenceTypes=normalized_evidence,
                )
            )
        elif ref == "ocr":
            sources.append(
                PlanNoteSource(type="image", ref=ref, evidenceTypes=["ocr"])
            )

    if include_provider and provider:
        provider_type = (
            "google_maps"
            if provider in {"google_maps", "google_maps_scraper"}
            else "place_provider"
        )
        fetched_at = provider_fetched_at
        if isinstance(fetched_at, str):
            try:
                fetched_at = datetime.fromisoformat(fetched_at)
            except ValueError:
                fetched_at = None
        sources.append(
            PlanNoteSource(
                type=provider_type,
                ref=provider_ref,
                fetchedAt=fetched_at,
            )
        )

    deduped: list[PlanNoteSource] = []
    seen_sources: set[tuple[str, str | None]] = set()
    for source in sources:
        key = (source.type, source.ref)
        if key in seen_sources:
            continue
        seen_sources.add(key)
        deduped.append(source)
    return deduped


def merge_note_sources(*groups: list[PlanNoteSource]) -> list[PlanNoteSource]:
    merged: list[PlanNoteSource] = []
    seen: set[tuple[str, str | None]] = set()
    for source in (source for group in groups for source in group):
        key = (source.type, source.ref)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged


def _clean_note_part(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    if not text:
        return None
    if len(text) > SOURCE_NOTE_PART_MAX_LENGTH:
        first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
        text = (
            first_sentence
            if len(first_sentence) <= SOURCE_NOTE_PART_MAX_LENGTH
            else text[: SOURCE_NOTE_PART_MAX_LENGTH + 1].rsplit(" ", 1)[0]
        ).rstrip(" ,;:-")
        text = f"{text}…"
    if text[-1] not in ".!?…":
        text = f"{text}."
    return text[0].upper() + text[1:] if text else None


def _dedupe_key(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()
