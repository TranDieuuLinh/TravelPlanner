from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from pydantic import BaseModel, Field


SOURCE_NOTE_MAX_LENGTH = 360
SOURCE_NOTE_PART_MAX_LENGTH = 180


class PlanNoteSource(BaseModel):
    """One read-only, source-owned note stored in a plan snapshot."""

    type: str = Field(min_length=1, max_length=40)
    text: str | None = Field(default=None, max_length=SOURCE_NOTE_MAX_LENGTH)
    evidence: str | None = Field(default=None, max_length=500)
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
    video_note: str | None = None,
    video_evidence: str | None = None,
) -> list[PlanNoteSource]:
    """Build independently displayable notes with their stable provenance."""

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
                    text=video_note,
                    evidence=video_evidence,
                    ref=ref,
                    evidenceTypes=normalized_evidence,
                )
            )
        elif ref == "ocr":
            sources.append(
                PlanNoteSource(type="image", ref=ref, evidenceTypes=["ocr"])
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


def compose_video_place_note(
    *,
    place_name: str,
    source_activity: str | None,
    source_evidence: dict[str, str] | None = None,
) -> str | None:
    """Return only useful creator context; provenance alone is not a note."""

    activity = _clean_note_part(source_activity)
    language_sample = (
        re.sub(re.escape(place_name), "", activity, flags=re.IGNORECASE)
        if activity
        else ""
    )
    if (
        not activity
        or not _looks_vietnamese(language_sample)
        or select_creator_story_evidence(
            place_name=place_name,
            source_evidence=source_evidence,
        )
        is None
    ):
        return None
    if _is_low_value_creator_note(activity, place_name=place_name):
        return None
    return _truncate_note(activity)


def select_creator_story_evidence(
    *,
    place_name: str,
    source_evidence: dict[str, str] | None,
) -> str | None:
    """Choose a place-scoped span that says more than the place name itself."""

    place_key = _ascii_note_key(place_name)
    candidates: list[tuple[int, str]] = []
    for value in (source_evidence or {}).values():
        evidence = " ".join(str(value).split()).strip()
        evidence_key = _ascii_note_key(evidence)
        if not evidence or not evidence_key:
            continue
        residue = evidence_key.replace(place_key, " ").strip() if place_key else evidence_key
        residue = re.sub(r"\s+", " ", residue)
        if len(residue) < 8:
            continue
        candidates.append((len(residue), evidence))
    return max(candidates, default=(0, ""), key=lambda item: item[0])[1] or None


def merge_note_sources(*groups: list[PlanNoteSource]) -> list[PlanNoteSource]:
    merged: list[PlanNoteSource] = []
    seen: set[tuple[str, str | None]] = set()
    for source in (source for group in groups for source in group):
        if source.type in {"google_maps", "place_provider"}:
            continue
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


def _truncate_note(value: str) -> str:
    if len(value) <= SOURCE_NOTE_MAX_LENGTH:
        return value
    shortened = value[: SOURCE_NOTE_MAX_LENGTH + 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return f"{shortened}…"


def _looks_vietnamese(value: str) -> bool:
    if re.search(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", value.casefold()):
        return True
    normalized = f" {value.casefold()} "
    return any(
        word in normalized
        for word in (
            " tham quan ",
            " khám phá ",
            " thưởng thức ",
            " ghé ",
            " ăn ",
            " uống ",
            " ngắm ",
            " thử ",
            " rút ",
        )
    )


def _is_low_value_creator_note(value: str, *, place_name: str) -> bool:
    """Reject labels and tautologies that do not help someone visit the place."""

    normalized = _ascii_note_key(value)
    normalized_name = _ascii_note_key(place_name)
    generic_patterns = (
        "video tham khao co nhac den",
        "video co nhac den",
        "creator co nhac den",
        "tham quan dia diem",
        "kham pha dia diem",
    )
    if any(pattern in normalized for pattern in generic_patterns):
        return True
    without_name = normalized.replace(normalized_name, "").strip() if normalized_name else normalized
    return without_name in {"", "tham quan", "kham pha", "ghe", "den"}


def _ascii_note_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold()).replace("đ", "d")
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        "".join(char for char in decomposed if not unicodedata.combining(char)),
    ).strip()
