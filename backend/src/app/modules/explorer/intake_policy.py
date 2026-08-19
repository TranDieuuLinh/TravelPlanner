from collections.abc import Callable, Iterable

from app.modules.explorer.contract import RequestedItem


_GENERAL_PREFERENCES = {
    "am thuc": "local_food",
    "ca phe": "coffee",
    "coffee": "coffee",
    "cuisine": "local_food",
    "culture": "culture",
    "di dao": "walking",
    "food": "local_food",
    "local experience": "local_experience",
    "nightlife": "nightlife",
    "trai nghiem dia phuong": "local_experience",
    "van hoa": "culture",
    "walk": "walking",
    "walking": "walking",
}
_PREFERENCE_CUES = (
    "interested in",
    "like",
    "prefer",
    "quan tam",
    "thich",
    "uu tien",
    "yeu thich",
)


def normalize_intake_items(
    items: Iterable[RequestedItem],
    preferences: Iterable[str],
    raw_prompt: str | None,
    *,
    normalize: Callable[[str], str],
) -> tuple[list[RequestedItem], list[str]]:
    """Keep resolvable requests as items and demote general tastes to preferences."""
    prompt_key = normalize(raw_prompt or "")
    normalized_items: list[RequestedItem] = []
    normalized_preferences = list(preferences)
    item_keys: set[tuple[str, str, str]] = set()

    for item in items:
        key = (normalize(item.name), item.action, normalize(item.related_place_name or ""))
        if normalize(item.evidence) not in prompt_key or key in item_keys:
            continue
        item_keys.add(key)
        preference = _general_preference(item, normalize)
        if preference is not None:
            normalized_preferences.append(preference)
        else:
            normalized_items.append(item)

    return normalized_items, list(dict.fromkeys(normalized_preferences))


def _general_preference(
    item: RequestedItem, normalize: Callable[[str], str]
) -> str | None:
    if item.related_place_name:
        return None
    name = normalize(item.name).strip(" ,.;:-")
    if name in _GENERAL_PREFERENCES:
        return _GENERAL_PREFERENCES[name]
    evidence = normalize(item.evidence)
    if any(cue in evidence for cue in _PREFERENCE_CUES):
        return name.replace(" ", "_")
    return None
