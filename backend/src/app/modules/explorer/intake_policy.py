from collections.abc import Callable, Iterable

from app.modules.explorer.contract import RequestedItem


def normalize_intake_items(
    items: Iterable[RequestedItem],
    preferences: Iterable[str],
    raw_prompt: str | None,
    *,
    normalize: Callable[[str], str],
) -> tuple[list[RequestedItem], list[str]]:
    """Validate item evidence and deduplicate; the LLM owns semantic categories."""
    prompt_key = normalize(raw_prompt or "")
    normalized_items: list[RequestedItem] = []
    normalized_preferences = list(preferences)
    item_keys: set[tuple[str, str, str]] = set()

    for item in items:
        key = (normalize(item.name), item.action, normalize(item.related_place_name or ""))
        if normalize(item.evidence) not in prompt_key or key in item_keys:
            continue
        item_keys.add(key)
        normalized_items.append(item)

    return normalized_items, list(dict.fromkeys(normalized_preferences))
