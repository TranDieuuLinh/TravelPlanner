"""Text normalization helpers shared by Knowledge Graph ingestion and search."""

from __future__ import annotations

import re
import unicodedata


_MOJIBAKE_MARKERS = frozenset(bytes(range(128, 256)).decode("cp437"))
_NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]+")


def normalize_knowledge_text(value: str) -> str:
    """Build the accent-insensitive lookup form used by graph indexes."""
    folded = value.strip().casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", folded)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def latin_transliteration(value: str) -> str:
    """Return a conservative Latin spelling for Vietnamese/Latin names."""
    folded = value.replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", folded)
    output = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character) and ord(character) < 128
    )
    return " ".join(output.split()).strip()


def repair_cp437_utf8_mojibake(value: str) -> str:
    """Repair the CP437-rendered UTF-8 corruption present in the legacy dump.

    The function is deliberately conservative: a decoded candidate is accepted
    only when it reduces the number of box-drawing/mojibake marker characters.
    """
    current = value
    for _ in range(2):
        before = _mojibake_score(current)
        if before == 0:
            break
        try:
            candidate = current.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if _mojibake_score(candidate) >= before:
            break
        current = candidate
    # A planning snapshot can combine already-correct Vietnamese evidence with
    # a corrupt provider description.  The whole string then cannot be encoded
    # as CP437.  Repair only contiguous non-ASCII byte-rendering runs, leaving
    # correct surrounding text untouched.
    return _NON_ASCII_RUN.sub(_repair_cp437_run, current)


def contains_mojibake(value: str) -> bool:
    return _mojibake_score(value) > 0


def _mojibake_score(value: str) -> int:
    return sum(character in _MOJIBAKE_MARKERS for character in value)


def _repair_cp437_run(match: re.Match[str]) -> str:
    value = match.group(0)
    before = _mojibake_score(value)
    if before == 0:
        return value
    try:
        candidate = value.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return candidate if _mojibake_score(candidate) < before else value
