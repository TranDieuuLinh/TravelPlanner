from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_SCHEMA_VERSION = "travel-source-record.v1"
GRAPH_SCHEMA_VERSION = "travel-knowledge-graph.v2"

SOURCE_AUTHORITY = {
    "unesco": 0.98,
    "dsvh": 0.95,
    "wikidata": 0.9,
    "vietnam_travel": 0.82,
    "wikivoyage": 0.78,
}

HERITAGE_RECORD_TYPES = {
    "unesco_heritage",
    "vietnam_cultural_heritage",
}


def load_normalized_records(input_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("schema_version") != SOURCE_SCHEMA_VERSION:
                    raise ValueError(
                        f"{path}:{line_number} uses unsupported schema "
                        f"{record.get('schema_version')!r}"
                    )
                records.append(record)
    return records


def build_operational_graph(
    base_graph: dict[str, Any],
    records: Iterable[dict[str, Any]],
    *,
    max_evidence_per_node: int = 8,
    built_at: str | None = None,
) -> dict[str, Any]:
    """Enrich an operational Planner/Finder graph with reviewed source evidence.

    The builder deliberately does not create Place nodes from article prose. It
    only links normalized source records to the existing area/theme/experience
    taxonomy using high-signal fields. Concrete Place identity remains owned by
    the Place catalog and Finder.
    """

    if max_evidence_per_node < 1:
        raise ValueError("max_evidence_per_node must be at least 1")

    region_aliases = [
        _normalize(value) for value in base_graph.get("regionAliases", []) if value
    ]
    if not region_aliases:
        raise ValueError("base graph must declare at least one regionAliases value")

    all_records = list(records)
    relevant: list[tuple[dict[str, Any], str, float]] = []
    for record in all_records:
        region_match = _match_region(record, region_aliases)
        if region_match is not None:
            relevant.append((record, *region_match))

    graph = json.loads(json.dumps(base_graph, ensure_ascii=False))
    graph["schemaVersion"] = GRAPH_SCHEMA_VERSION
    sources_by_id: dict[str, dict[str, Any]] = {}

    for node in graph.get("nodes", []):
        matches: list[dict[str, Any]] = []
        for record, region_method, region_confidence in relevant:
            node_match = _match_node(record, node)
            if node_match is None:
                continue
            node_method, node_confidence = node_match
            source_id = str(record["record_id"])
            confidence = round(
                min(
                    SOURCE_AUTHORITY.get(str(record.get("source")), 0.7),
                    region_confidence,
                    node_confidence,
                ),
                3,
            )
            matches.append(
                {
                    "sourceId": source_id,
                    "confidence": confidence,
                    "matchMethod": f"{region_method}+{node_method}",
                }
            )
            sources_by_id[source_id] = _source_metadata(record)

        matches.sort(key=lambda value: (-value["confidence"], value["sourceId"]))
        if matches:
            node["evidenceRefs"] = matches[:max_evidence_per_node]
        else:
            node.pop("evidenceRefs", None)

    linked_source_ids = {
        ref["sourceId"]
        for node in graph.get("nodes", [])
        for ref in node.get("evidenceRefs", [])
    }
    graph["sources"] = [
        sources_by_id[source_id] for source_id in sorted(linked_source_ids)
    ]
    evidenced_nodes = [
        node for node in graph.get("nodes", []) if node.get("evidenceRefs")
    ]
    graph["build"] = {
        "builtAt": built_at or datetime.now(timezone.utc).isoformat(),
        "sourceSchemaVersion": SOURCE_SCHEMA_VERSION,
        "inputRecordCount": len(all_records),
        "regionRelevantRecordCount": len(relevant),
        "linkedSourceCount": len(linked_source_ids),
        "unlinkedRegionRelevantRecordCount": len(relevant) - len(linked_source_ids),
        "evidencedNodeCount": len(evidenced_nodes),
        "evidenceLinkCount": sum(
            len(node["evidenceRefs"]) for node in evidenced_nodes
        ),
        "method": "deterministic-high-signal-linking.v1",
    }
    return graph


def write_graph(path: Path, graph: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _match_region(
    record: dict[str, Any], region_aliases: list[str]
) -> tuple[str, float] | None:
    payload = record.get("payload") or {}
    structured_values = [
        *record.get("destination_hints", []),
        payload.get("adminLabel", ""),
    ]
    if _values_contain_alias(structured_values, region_aliases):
        return "structured-region", 0.98
    if _values_contain_alias(
        [record.get("title", ""), record.get("source_url", "")], region_aliases
    ):
        return "title-or-url-region", 0.9
    return None


def _match_node(
    record: dict[str, Any], node: dict[str, Any]
) -> tuple[str, float] | None:
    terms = [
        _normalize(value)
        for value in (
            node.get("evidenceTerms")
            or (
                node.get("label", ""),
                *node.get("aliases", []),
                *node.get("searchTerms", []),
            )
        )
        if value and len(_normalize(value)) >= 3
    ]
    if not terms:
        return None

    payload = record.get("payload") or {}
    structured_values = [
        payload.get("itemLabel", ""),
        payload.get("typeLabel", ""),
        payload.get("queryGroup", ""),
    ]
    if node.get("kind") == "area":
        structured_values.append(payload.get("itemDescription", ""))
    if _values_contain_alias(structured_values, terms):
        return "structured-node", 0.94

    if _values_contain_alias([record.get("title", "")], terms):
        return "title-node", 0.9

    url_terms = [term for term in terms if len(term) >= 4]
    if _values_contain_alias([record.get("source_url", "")], url_terms):
        return "url-node", 0.84

    section_headings = payload.get("sections", {})
    if isinstance(section_headings, dict) and _values_contain_alias(
        section_headings.keys(), terms
    ):
        return "section-node", 0.78

    if (
        node.get("id") == "theme:heritage"
        and record.get("record_type") in HERITAGE_RECORD_TYPES
    ):
        return "authority-heritage-record", 0.92
    return None


def _source_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(record["record_id"]),
        "sourceName": str(record.get("source", "")),
        "title": str(record.get("title", "")),
        "sourceUrl": str(record.get("source_url", "")),
        "license": str(record.get("license", "")),
        "retrievedAt": str(record.get("retrieved_at", "")),
        "contentSha256": str(record.get("content_sha256", "")),
        "recordType": str(record.get("record_type", "")),
    }


def _values_contain_alias(values: Iterable[Any], aliases: list[str]) -> bool:
    return any(
        _contains_phrase(_normalize(value), alias)
        for value in values
        if value
        for alias in aliases
        if alias
    )


def _normalize(value: Any) -> str:
    # Evidence linking is intentionally accent-sensitive. Folding Vietnamese
    # diacritics makes "phở" collide with "thành phố" and "đền" with "đến",
    # which produces confident but false provenance edges.
    return " ".join(
        "".join(
            char if char.isalnum() else " "
            for char in str(value).strip().casefold()
        ).split()
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    return f" {phrase} " in f" {text} "
