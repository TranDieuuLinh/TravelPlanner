from __future__ import annotations

import json
import unicodedata
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol


TRAVERSABLE_RELATIONS = {"SUPPORTS_THEME", "INCLUDES_EXPERIENCE"}


@dataclass(frozen=True)
class TravelGraphExpansion:
    matched_node_ids: tuple[str, ...] = ()
    experience_node_ids: tuple[str, ...] = ()
    query_terms: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    diversity_groups: tuple[str, ...] = ()


class TravelKnowledgeSearchTool(Protocol):
    def expand(
        self,
        signals: list[str],
        *,
        region_key: str,
        max_depth: int = 3,
        category: str | None = None,
    ) -> TravelGraphExpansion: ...

    def classify_experience(
        self,
        signals: list[str],
        *,
        region_key: str,
        category: str | None = None,
    ) -> str | None: ...


class JsonTravelKnowledgeSearchTool:
    """Small versioned knowledge graph with a storage-neutral interface.

    The JSON implementation is deliberately simple for the MVP. A future
    Neo4j, Apache AGE or RDF adapter only needs to implement the same two
    methods; Planner/Finder do not depend on a graph database vendor.
    """

    def __init__(self, payload: dict) -> None:
        self.schema_version = str(payload["schemaVersion"])
        self.region_key = str(payload["regionKey"])
        self.nodes = {str(node["id"]): node for node in payload.get("nodes", [])}
        self.outgoing: dict[str, list[dict]] = {}
        for edge in payload.get("edges", []):
            self.outgoing.setdefault(str(edge["source"]), []).append(edge)

    @classmethod
    def from_path(cls, path: Path) -> "JsonTravelKnowledgeSearchTool":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def expand(
        self,
        signals: list[str],
        *,
        region_key: str,
        max_depth: int = 3,
        category: str | None = None,
    ) -> TravelGraphExpansion:
        if not self._supports_region(region_key):
            return TravelGraphExpansion()
        normalized_signals = [_normalize(signal) for signal in signals if signal]
        matched = [
            node_id
            for node_id, node in self.nodes.items()
            if node.get("kind") != "destination"
            and self._matches_node(node, normalized_signals)
        ]
        if not matched:
            return TravelGraphExpansion()

        visited = set(matched)
        queue = deque((node_id, 0) for node_id in matched)
        while queue:
            node_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for edge in self.outgoing.get(node_id, []):
                if edge.get("relation") not in TRAVERSABLE_RELATIONS:
                    continue
                target = str(edge["target"])
                if target in visited:
                    continue
                visited.add(target)
                queue.append((target, depth + 1))

        experiences = [
            self.nodes[node_id]
            for node_id in visited
            if self.nodes[node_id].get("kind") == "experience"
            and (
                category is None
                or self.nodes[node_id].get("placeCategory") == category
            )
        ]
        experiences.sort(key=lambda node: (-float(node.get("weight", 1.0)), node["id"]))
        return TravelGraphExpansion(
            matched_node_ids=tuple(matched),
            experience_node_ids=tuple(str(node["id"]) for node in experiences),
            query_terms=_unique(
                term
                for node in experiences
                for term in (node.get("label", ""), *node.get("searchTerms", []))
                if term
            ),
            categories=_unique(
                str(node["placeCategory"])
                for node in experiences
                if node.get("placeCategory")
            ),
            diversity_groups=_unique(
                str(node["diversityGroup"])
                for node in experiences
                if node.get("diversityGroup")
            ),
        )

    def classify_experience(
        self,
        signals: list[str],
        *,
        region_key: str,
        category: str | None = None,
    ) -> str | None:
        if not self._supports_region(region_key):
            return None
        normalized_signals = [_normalize(signal) for signal in signals if signal]
        matches = [
            node
            for node in self.nodes.values()
            if node.get("kind") == "experience"
            and node.get("diversityGroup")
            and (category is None or node.get("placeCategory") == category)
            and self._matches_node(node, normalized_signals)
        ]
        if not matches:
            return None
        matches.sort(key=lambda node: (-self._specificity(node), -float(node.get("weight", 1.0))))
        return str(matches[0]["diversityGroup"])

    def _supports_region(self, region_key: str) -> bool:
        return region_key == self.region_key or region_key.startswith(f"{self.region_key},")

    @staticmethod
    def _node_terms(node: dict) -> tuple[str, ...]:
        return tuple(
            _normalize(value)
            for value in (
                node.get("label", ""),
                *node.get("aliases", []),
                *node.get("searchTerms", []),
            )
            if value
        )

    def _matches_node(self, node: dict, signals: list[str]) -> bool:
        terms = self._node_terms(node)
        return any(
            term and _contains_phrase(signal, term)
            for signal in signals
            for term in terms
        )

    def _specificity(self, node: dict) -> int:
        return max((len(term.split()) for term in self._node_terms(node)), default=0)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.strip().casefold())
    ascii_text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return " ".join(
        "".join(char if char.isalnum() else " " for char in ascii_text).split()
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "


def _unique(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@lru_cache(maxsize=1)
def get_default_travel_knowledge_tool() -> JsonTravelKnowledgeSearchTool:
    return JsonTravelKnowledgeSearchTool.from_path(
        Path(__file__).with_name("hanoi_graph.v1.json")
    )
