import re
import unicodedata


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_text = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    ).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def lookup_names(query: str, alternate_names: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for value in [query, *alternate_names]:
        key = normalize_text(value)
        if key and key not in seen:
            names.append(value.strip())
            seen.add(key)
        if len(names) == 2:
            break
    return names

