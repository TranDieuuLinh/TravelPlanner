from app.shared.tools.search_places.normalization import normalize_text


LABEL_ALIASES = {
    "nightlife": {
        "nightlife",
        "trai nghiem do uong buoi toi",
        "pho bia",
        "beer street",
        "bar",
        "pub",
        "karaoke",
        "casino",
    },
    "alcohol": {"alcohol", "bia", "beer", "cocktail", "ruou"},
    "crowded_places": {"crowded places", "dong duc"},
    "local_food": {"local food", "dung bua", "an pho", "bun cha", "banh mi"},
    "culture": {"culture", "van hoa", "tin nguong", "bao tang"},
    "outdoor": {"outdoor", "di dao ngoai troi", "cam trai"},
    "family_friendly": {"family friendly", "vui choi danh cho tre em"},
    "traditional_drinks": {"traditional drinks", "uong tra", "uong ca phe"},
    "sunset_views": {"sunset views", "ngam hoang hon"},
}


def canonical_label(value: str) -> str:
    normalized = normalize_text(value)
    for prefix in ("experience ", "item "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    for canonical, aliases in LABEL_ALIASES.items():
        if any(
            normalized == alias
            or f" {alias} " in f" {normalized} "
            for alias in aliases
        ):
            return canonical
    return normalized.replace(" ", "_")


def canonical_labels(values: list[str] | set[str]) -> set[str]:
    return {canonical_label(value) for value in values if normalize_text(value)}
