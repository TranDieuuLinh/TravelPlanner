from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


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
) -> str:
    """Link only names confirmed by the Knowledge Graph resolver."""
    if resolver is None:
        return text

    resolved_names: list[str] = []
    seen: set[str] = set()
    for name in entity_names:
        candidate = " ".join(name.split())
        folded = candidate.casefold()
        if not candidate or folded in seen:
            continue
        seen.add(folded)
        if await resolver.resolve(candidate) is not None:
            resolved_names.append(candidate)

    linked = text
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
