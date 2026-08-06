"""Conservative address normalization for place identity checks."""

from __future__ import annotations

import re
import unicodedata


_PLUS_CODE = re.compile(
    r"\b[23456789CFGHJMPQRVWX]{4,8}\+[23456789CFGHJMPQRVWX]{2,3}\b",
    re.I,
)
_POSTAL_CODE = re.compile(r"\b\d{5,6}\b")
_HOUSE_NUMBER = re.compile(
    r"(?<!\w)(\d{1,4})(?:\s*[-/]\s*([a-z])|([a-z]))?(?!\w)",
    re.I,
)
_STRUCTURAL_TOKENS = frozenset(
    {
        "city",
        "district",
        "duong",
        "ha",
        "hanoi",
        "nam",
        "noi",
        "phuong",
        "pho",
        "quan",
        "road",
        "street",
        "thanh",
        "tp",
        "vietnam",
        "viet",
        "ward",
    }
)


def normalize_address(value: str | None) -> str:
    """Return an accent-insensitive comparison form without routing noise."""
    if not value:
        return ""
    cleaned = _POSTAL_CODE.sub(" ", _PLUS_CODE.sub(" ", value))
    cleaned = re.sub(r"\b(?:no|number)\.?\s+(?=\d)", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\bđ\.(?=\s)", " duong ", cleaned, flags=re.I)
    cleaned = re.sub(r"\bp\.(?=\s)", " pho ", cleaned, flags=re.I)
    cleaned = re.sub(r"\bng\.(?=\s)", " ngo ", cleaned, flags=re.I)
    decomposed = unicodedata.normalize(
        "NFKD", cleaned.casefold().replace("đ", "d")
    )
    folded = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", folded).split())


def address_numbers(value: str | None) -> set[str]:
    """Extract house numbers while excluding plus codes and postal codes."""
    if not value:
        return set()
    cleaned = _POSTAL_CODE.sub(" ", _PLUS_CODE.sub(" ", value))
    return {
        f"{number}{(hyphen_suffix or direct_suffix).casefold()}"
        for number, hyphen_suffix, direct_suffix in _HOUSE_NUMBER.findall(cleaned)
    }


def address_tokens(value: str | None) -> set[str]:
    """Extract meaningful locality/street tokens for conflict detection."""
    numbers = address_numbers(value)
    return {
        token
        for token in normalize_address(value).split()
        if token not in _STRUCTURAL_TOKENS
        and token not in numbers
        and not token.isdigit()
        and len(token) >= 3
    }
