from __future__ import annotations

import re
import unicodedata
from collections import Counter
from urllib.parse import parse_qs, urlsplit


_VIETNAM_REGIONS = {
    "ha noi": "Hanoi",
    "hanoi": "Hanoi",
    "da nang": "Da Nang",
    "danang": "Da Nang",
    "ho chi minh": "Ho Chi Minh City",
    "hochiminh": "Ho Chi Minh City",
    "hoi an": "Hoi An",
    "hoian": "Hoi An",
    "hue": "Hue",
    "ninh binh": "Ninh Binh",
    "ninhbinh": "Ninh Binh",
    "da lat": "Da Lat",
    "sa pa": "Sa Pa",
    "sapa": "Sa Pa",
}
_UNKNOWN_REGIONS = {"", "unspecified", "unknown", "none", "null", "n/a"}


def usable_destination(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split()).strip(" ,")
    if _ascii_words(cleaned) in _UNKNOWN_REGIONS:
        return None
    return cleaned or None


def infer_destination_from_urls(urls: list[str]) -> str:
    for url in urls:
        query = parse_qs(urlsplit(url).query)
        for value in query.get("q", []):
            match = re.search(
                r"(?:what\s+to\s+do|things\s+to\s+do)\s+in\s+"
                r"(.+?)(?:[?!]|$)",
                value,
                flags=re.IGNORECASE,
            )
            if match:
                return " ".join(match.group(1).split()).strip().title()
            inferred = infer_destination_from_text(value)
            if inferred:
                return inferred
    return ""


def infer_destination_from_text(*values: str | None) -> str:
    text = " ".join(value for value in values if value)
    normalized = _ascii_words(text)
    if not normalized:
        return ""
    counts: Counter[str] = Counter()
    for alias, display in _VIETNAM_REGIONS.items():
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            counts[display] += 1
    return counts.most_common(1)[0][0] if counts else ""


def infer_destination_from_place_names(names: list[str]) -> str:
    counts: Counter[str] = Counter()
    for name in names:
        normalized = _ascii_words(name)
        for alias, display in _VIETNAM_REGIONS.items():
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                counts[display] += 1
    if not counts:
        return ""
    display, count = counts.most_common(1)[0]
    return display if count >= 1 else ""


def _ascii_words(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    ascii_text = "".join(
        character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))
