from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from urllib.parse import quote


class EntityResolver:
    def __init__(self, lookup: Callable[[str], Awaitable[dict | None]]) -> None:
        self.lookup = lookup

    async def resolve(self, name: str) -> tuple[str, str] | None:
        normalized = " ".join(name.split())
        if not normalized:
            return None
        try:
            result = await self.lookup(normalized)
        except Exception:
            return None
        if not result or not result.get("id"):
            return None
        return str(result.get("name") or normalized), str(result["id"])


async def link_verified_entities(
    text: str, entity_names: list[str], resolver: EntityResolver | None
) -> str:
    if resolver is None or not entity_names:
        return text
    resolved: list[tuple[str, str]] = []
    for name in entity_names:
        display = " ".join(name.split())
        if not display:
            continue
        result = await resolver.resolve(display)
        if result:
            resolved.append((display, result[1]))
    if not resolved:
        return text
    pattern = text
    for display, entity_id in sorted(resolved, key=lambda item: len(item[0]), reverse=True):
        entity_href = f"travel-entity://entity/{quote(entity_id, safe='')}"
        # Replace an already-generated markdown link whose label is this
        # entity. This prevents accidental planner/chat URLs from surviving.
        pattern = re.sub(
            rf"\[({re.escape(display)})\]\([^)]*\)",
            rf"[\1]({entity_href})",
            pattern,
            flags=re.IGNORECASE,
        )
        pattern = re.sub(
            rf"(?<![\w])({re.escape(display)})(?![\w])",
            lambda match: f"[{match.group(1)}]({entity_href})",
            pattern,
            flags=re.IGNORECASE,
        )
    return pattern
