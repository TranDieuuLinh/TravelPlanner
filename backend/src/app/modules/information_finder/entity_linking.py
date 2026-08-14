from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.modules.information_finder.contract import EntityCandidate


_MARKDOWN_LINK = re.compile(
    r"(?<!!)\[([^\]]+)\]\([^\s)]+(?:\s+[^)]*)?\)",
)


@dataclass(frozen=True)
class ResolvedEntity:
    name: str
    entity_id: str


class EntityResolver:
    """Port for resolving a display name against the Knowledge Graph."""

    async def resolve(self, name: str) -> ResolvedEntity | None:
        raise NotImplementedError


class KnowledgeGraphEntityResolver(EntityResolver):
    """Adapter around the public Knowledge Graph entity-preview operation."""

    def __init__(self, lookup: Callable[[str], Awaitable[dict | None]]) -> None:
        self.lookup = lookup

    async def resolve(self, name: str) -> ResolvedEntity | None:
        normalized = " ".join(name.split())
        if not normalized:
            return None
        try:
            result = await self.lookup(normalized)
        except Exception:
            return None
        if not result or not result.get("id"):
            return None
        return ResolvedEntity(
            name=str(result.get("name") or normalized),
            entity_id=str(result["id"]),
        )


async def link_verified_entities(
    text: str,
    entity_names: list[str],
    resolver: EntityResolver | None,
    entity_candidates: list[EntityCandidate] | None = None,
) -> str:
    """Link only names confirmed by the Knowledge Graph resolver."""
    if resolver is None:
        return text

    linked_labels = [match.group(1).strip() for match in _MARKDOWN_LINK.finditer(text)]
    candidates: list[tuple[str, list[str]]] = [
        (candidate.display_name, candidate.lookup_names)
        for candidate in (entity_candidates or [])
    ]
    candidates.extend((name, [name]) for name in entity_names)
    candidates.extend((label, [label]) for label in linked_labels)
    resolved_names: list[str] = []
    seen: set[str] = set()
    for display_name, lookup_names in candidates:
        display = " ".join(display_name.split())
        folded = display.casefold()
        if not display or folded in seen:
            continue
        seen.add(folded)
        for lookup_name in [display, *lookup_names]:
            lookup = " ".join(lookup_name.split())
            if lookup and await resolver.resolve(lookup) is not None:
                resolved_names.append(display)
                break

    linked = _MARKDOWN_LINK.sub(lambda match: match.group(1), text)
    for name in sorted(resolved_names, key=len, reverse=True):
        pattern = re.compile(
            rf"(?<![\w])({re.escape(name)})(?![\w])",
            re.IGNORECASE,
        )
        linked = pattern.sub(
            lambda match: f"[{match.group(1)}](travel-entity://entity)",
            linked,
        )
    return linked
