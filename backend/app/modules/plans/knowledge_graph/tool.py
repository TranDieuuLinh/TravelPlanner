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
    region_keys: tuple[str, ...] = ()
    source_evidence: tuple["TravelGraphSourceEvidence", ...] = ()


@dataclass(frozen=True)
class TravelGraphSourceEvidence:
    source_id: str
    source_name: str
    title: str
    source_url: str
    license: str
    retrieved_at: str
    confidence: float
    node_ids: tuple[str, ...] = ()


class TravelKnowledgeSearchTool(Protocol):
    def supports_region(self, region_key: str) -> bool: ...

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
        _validate_payload(payload)
        self.schema_version = str(payload["schemaVersion"])
        self.region_key = str(payload["regionKey"])
        self.nodes = {str(node["id"]): node for node in payload.get("nodes", [])}
        self.sources = {
            str(source["id"]): source for source in payload.get("sources", [])
        }
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
        if not self.supports_region(region_key):
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
            region_keys=_unique(
                str(region_key)
                for node_id in matched
                for region_key in self.nodes[node_id].get("regionKeys", [])
                if region_key
            ),
            source_evidence=self._source_evidence(
                [*matched, *(str(node["id"]) for node in experiences)]
            ),
        )

    def classify_experience(
        self,
        signals: list[str],
        *,
        region_key: str,
        category: str | None = None,
    ) -> str | None:
        if not self.supports_region(region_key):
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

    def supports_region(self, region_key: str) -> bool:
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

    def _source_evidence(
        self, node_ids: list[str], *, limit: int = 8
    ) -> tuple[TravelGraphSourceEvidence, ...]:
        evidence_by_source: dict[str, dict] = {}
        for node_id in node_ids:
            node = self.nodes.get(node_id, {})
            for ref in node.get("evidenceRefs", []):
                source_id = str(ref.get("sourceId", ""))
                source = self.sources.get(source_id)
                if source is None:
                    continue
                current = evidence_by_source.setdefault(
                    source_id,
                    {
                        "source": source,
                        "confidence": 0.0,
                        "node_ids": [],
                    },
                )
                current["confidence"] = max(
                    float(current["confidence"]),
                    float(ref.get("confidence", 0.0)),
                )
                current["node_ids"].append(node_id)

        ranked = sorted(
            evidence_by_source.items(),
            key=lambda item: (-float(item[1]["confidence"]), item[0]),
        )[:limit]
        return tuple(
            TravelGraphSourceEvidence(
                source_id=source_id,
                source_name=str(value["source"].get("sourceName", "")),
                title=str(value["source"].get("title", "")),
                source_url=str(value["source"].get("sourceUrl", "")),
                license=str(value["source"].get("license", "")),
                retrieved_at=str(value["source"].get("retrievedAt", "")),
                confidence=float(value["confidence"]),
                node_ids=_unique(value["node_ids"]),
            )
            for source_id, value in ranked
        )


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


def _validate_payload(payload: dict) -> None:
    if not payload.get("schemaVersion") or not payload.get("regionKey"):
        raise ValueError("Knowledge Graph requires schemaVersion and regionKey.")
    nodes = payload.get("nodes", [])
    node_ids = [str(node.get("id", "")) for node in nodes]
    if any(
        not node_id or not node.get("kind") or not node.get("label")
        for node_id, node in zip(node_ids, nodes, strict=True)
    ):
        raise ValueError("Every Knowledge Graph node requires id, kind and label.")
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Knowledge Graph node ids must be unique.")
    known_nodes = set(node_ids)
    sources = payload.get("sources", [])
    source_ids = [str(source.get("id", "")) for source in sources]
    if any(
        not source_id
        or not source.get("sourceName")
        or not source.get("sourceUrl")
        or not source.get("license")
        or not source.get("retrievedAt")
        or not source.get("contentSha256")
        for source_id, source in zip(source_ids, sources, strict=True)
    ):
        raise ValueError(
            "Every Knowledge Graph source requires provenance metadata."
        )
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Knowledge Graph source ids must be unique.")
    known_sources = set(source_ids)
    for edge in payload.get("edges", []):
        if str(edge.get("source", "")) not in known_nodes or str(
            edge.get("target", "")
        ) not in known_nodes:
            raise ValueError("Knowledge Graph edges must reference existing nodes.")
    for node in payload.get("nodes", []):
        for ref in node.get("evidenceRefs", []):
            if str(ref.get("sourceId", "")) not in known_sources:
                raise ValueError(
                    "Knowledge Graph evidenceRefs must reference existing sources."
                )


@lru_cache(maxsize=1)
def get_default_travel_knowledge_tool() -> JsonTravelKnowledgeSearchTool:
    return JsonTravelKnowledgeSearchTool.from_path(
        Path(__file__).with_name("hanoi_graph.v2.json")
    )
