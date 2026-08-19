from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import quote

from app.modules.information_finder.contract import (
    AnswerBlock,
    ComparisonBlock,
    EntityCandidate,
    FactListBlock,
    RecommendationsBlock,
    StepsBlock,
    VerseBlock,
)
from app.modules.information_finder.structured_blocks import EntitySpan, TextSpan


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

    candidates: list[tuple[str, list[str]]] = [
        (candidate.display_name, candidate.lookup_names)
        for candidate in (entity_candidates or [])
    ]
    candidates.extend((name, [name]) for name in entity_names)
    resolved_entities: dict[str, tuple[str, ResolvedEntity]] = {}
    for display_name, lookup_names in candidates:
        display = " ".join(display_name.split())
        folded = display.casefold()
        if not display or folded in resolved_entities:
            continue
        for lookup_name in [display, *lookup_names]:
            lookup = " ".join(lookup_name.split())
            if lookup:
                resolved = await resolver.resolve(lookup)
                if resolved is not None and resolved.entity_id:
                    resolved_entities[folded] = (display, resolved)
                    break

    if not resolved_entities:
        return text

    # Protect existing Markdown links (including citations already rendered by
    # another layer) so entity replacement cannot turn their labels into links
    # or alter their destinations.
    protected_links: list[str] = []

    def protect_link(match: re.Match[str]) -> str:
        protected_links.append(match.group(0))
        return f"\x00LINK_{len(protected_links) - 1}\x00"

    linked = _MARKDOWN_LINK.sub(protect_link, text)
    for display_name, entity in sorted(
        resolved_entities.values(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        pattern = re.compile(
            rf"(?<![\w])({re.escape(display_name)})(?![\w])",
            re.IGNORECASE,
        )
        linked = pattern.sub(
            lambda match: (
                f"[{match.group(1)}](travel-entity://entity/"
                f"{quote(entity.entity_id, safe='')})"
            ),
            linked,
        )
    for index, original in enumerate(protected_links):
        linked = linked.replace(f"\x00LINK_{index}\x00", original)
    return linked


async def materialize_entity_spans(
    blocks: list[AnswerBlock],
    *,
    entity_names: list[str],
    entity_candidates: list[EntityCandidate],
    resolver: EntityResolver | None,
) -> list[AnswerBlock]:
    """Add safe entity spans to blocks after Knowledge Graph resolution."""
    resolved_patterns = await _resolve_patterns(
        entity_names, entity_candidates, resolver
    )
    return [_materialize_block(block, resolved_patterns) for block in blocks]


async def _resolve_patterns(
    entity_names: list[str],
    entity_candidates: list[EntityCandidate],
    resolver: EntityResolver | None,
) -> list[tuple[str, ResolvedEntity]]:
    if resolver is None:
        return []
    candidates: list[tuple[str, list[str]]] = [
        (candidate.display_name, candidate.lookup_names)
        for candidate in entity_candidates
    ]
    candidates.extend((name, [name]) for name in entity_names)
    resolved: list[tuple[str, ResolvedEntity]] = []
    seen: set[tuple[str, str]] = set()
    for display_name, lookup_names in candidates:
        display = " ".join(display_name.split())
        if not display:
            continue
        for lookup_name in [display, *lookup_names]:
            lookup = " ".join(lookup_name.split())
            result = await resolver.resolve(lookup)
            if result is None or not result.entity_id:
                continue
            key = (display.casefold(), result.entity_id)
            if key not in seen:
                resolved.append((display, result))
                seen.add(key)
            break
    return sorted(resolved, key=lambda item: len(item[0]), reverse=True)


def _materialize_block(block: AnswerBlock, patterns):
    if isinstance(block, VerseBlock):
        text = "\n".join(block.lines)
        return block.model_copy(update={"inline_spans": _inline_spans(text, patterns)})
    if isinstance(block, (FactListBlock, RecommendationsBlock, StepsBlock, ComparisonBlock)):
        field = "options" if isinstance(block, ComparisonBlock) else "items"
        children = [
            child.model_copy(
                update={
                    "inline_spans": _inline_spans(
                        _item_text(child), patterns
                    )
                }
            )
            for child in getattr(block, field)
        ]
        return block.model_copy(update={field: children})
    if hasattr(block, "text"):
        return block.model_copy(
            update={"inline_spans": _inline_spans(block.text, patterns)}
        )
    return block


def _item_text(item) -> str:
    if hasattr(item, "text"):
        return item.text
    if hasattr(item, "reason"):
        return f"{item.name}: {item.reason}"
    if hasattr(item, "pros"):
        pros = ", ".join(item.pros)
        cons = ", ".join(item.cons)
        return f"{item.name}: Ưu: {pros}; Lưu ý: {cons}"
    return ""


def _inline_spans(text: str, patterns: list[tuple[str, ResolvedEntity]]):
    if not text:
        return []
    matches: list[tuple[int, int, ResolvedEntity]] = []
    for display, entity in patterns:
        pattern = re.compile(
            rf"(?<![\w]){re.escape(display)}(?![\w])", re.IGNORECASE
        )
        matches.extend(
            (match.start(), match.end(), entity)
            for match in pattern.finditer(text)
        )
    if not matches:
        return [TextSpan(text=text)]
    spans = []
    cursor = 0
    for start, end, entity in sorted(
        matches, key=lambda item: (item[0], -(item[1] - item[0]))
    ):
        if start < cursor:
            continue
        if start > cursor:
            spans.append(TextSpan(text=text[cursor:start]))
        spans.append(EntitySpan(text=text[start:end], entity_id=entity.entity_id))
        cursor = end
    if cursor < len(text):
        spans.append(TextSpan(text=text[cursor:]))
    return spans
