from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import sys
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT
sys.path.insert(0, str(BACKEND_ROOT))
# Script chỉ thao tác file Knowledge Graph; tránh để cấu hình place resolver cũ
# trong .env chặn việc nạp BACKEND_ROOT từ app.core.config.
os.environ["PLACE_RESOLVER_PROVIDER"] = "provisional"

from app.modules.knowledge_graph.dataset import KnowledgeGraphDataset  # noqa: E402
from app.modules.knowledge_graph.repository import GraphImportRepository  # noqa: E402


PLACE_TYPES = {"TravelPlace", "Restaurant", "DrinkDessert", "Accommodation"}
SOURCE_KEY = "hanoi_travel_relational_20260802"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Đưa graph đã chuẩn hóa vào hàng đợi AI Import để admin duyệt.",
    )
    parser.add_argument(
        "--candidate-dir",
        type=Path,
        default=WORKSPACE_ROOT / "trung-temp" / "knowledge-graph-real",
    )
    parser.add_argument(
        "--graph-dir",
        type=Path,
        default=WORKSPACE_ROOT / "knowledge-graph-real-v2",
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=BACKEND_ROOT / "var" / "knowledge-graph-imports.json",
    )
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def read_csv(directory: Path, name: str) -> list[dict[str, str]]:
    with (directory / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def chunks(values: list[object], size: int) -> list[list[object]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def version(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def temp_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:20]}"


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def parse_recommendations(value: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def build_jobs(
    candidate_dir: Path,
    dataset: KnowledgeGraphDataset,
    repository: GraphImportRepository,
    batch_size: int,
) -> tuple[list[dict], dict[str, object]]:
    entities = read_csv(candidate_dir, "entities.csv")
    properties = read_csv(candidate_dir, "properties.csv")
    aliases = read_csv(candidate_dir, "aliases.csv")
    relationships = read_csv(candidate_dir, "relationships.csv")
    entity_by_id = {row["id"]: row for row in entities}
    properties_by_entity: dict[str, dict[str, str]] = defaultdict(dict)
    aliases_by_entity: dict[str, list[str]] = defaultdict(list)
    for row in properties:
        properties_by_entity[row["entity_id"]][row["key"]] = row["value"]
    for row in aliases:
        aliases_by_entity[row["entity_id"]].append(row["alias"])

    schema, ontology = dataset.raw_contract()
    dataset_hash = dataset.hash()
    base_time = datetime.now(timezone.utc)
    jobs: list[dict] = []
    covered_entities: set[str] = set()
    covered_edges: set[str] = set()

    existing_entities = dataset.entities()
    existing_aliases: dict[str, list[str]] = defaultdict(list)
    for row in dataset.aliases():
        existing_aliases[row.get("entity_id", "")].append(row.get("alias", ""))
    existing_edges = {
        (row.get("from_entity_id"), row.get("relationship"), row.get("to_entity_id"))
        for row in dataset.relationships()
    }
    required_by_type = {
        node_type: sorted(dataset.required_properties(node_type))
        for node_type in {row["type"] for row in entities}
    }
    optional_by_type = {
        node_type: sorted(dataset.optional_properties(node_type))
        for node_type in {row["type"] for row in entities}
    }
    node_templates: dict[str, dict] = {}

    def node(entity_id: str) -> dict:
        if entity_id in node_templates:
            return copy.deepcopy(node_templates[entity_id])
        entity = entity_by_id[entity_id]
        proposed_name = normalized(entity["name"])
        candidates = []
        for existing in existing_entities:
            existing_name = normalized(existing.get("name", ""))
            alias_names = {
                normalized(value)
                for value in existing_aliases.get(existing.get("id", ""), [])
            }
            rules: list[str] = []
            score = 0
            if proposed_name and proposed_name == existing_name:
                rules.append("name_exact")
                score = 95
            elif proposed_name and proposed_name in alias_names:
                rules.append("alias_exact")
                score = 92
            if proposed_name and existing_name and score < 95:
                similarity = SequenceMatcher(None, proposed_name, existing_name).ratio()
                if similarity >= 0.78:
                    rules.append(f"name_similarity:{similarity:.2f}")
                    score = max(score, round(similarity * 85))
            if score:
                candidates.append({
                    "entity_id": existing.get("id", ""),
                    "canonical_name": existing.get("name", ""),
                    "type": existing.get("type", ""),
                    "score": score,
                    "matched_rules": rules,
                })
        candidates.sort(key=lambda item: item["score"], reverse=True)
        match_status = (
            "existing" if candidates and candidates[0]["score"] >= 95
            else "possible_duplicate" if candidates and candidates[0]["score"] >= 65
            else "new"
        )
        issues = []
        missing = set(required_by_type[entity["type"]]) - set(properties_by_entity.get(entity_id, {}))
        issues.extend(f"required_property_missing:{key}" for key in sorted(missing))
        result = {
            "temp_id": temp_id("n", entity_id),
            "entity_id": entity_id,
            "type": entity["type"],
            "canonical_name": entity["name"],
            "aliases": aliases_by_entity.get(entity_id, []),
            "properties": properties_by_entity.get(entity_id, {}),
            "evidence": [f"Bản ghi chuẩn hóa {entity_id} từ {SOURCE_KEY}."],
            "confidence": 0.9,
            "match_status": match_status,
            "match_candidates": candidates[:5],
            "selected_entity_id": candidates[0]["entity_id"] if match_status == "existing" else None,
            "decision": "pending",
            "validation_issues": issues,
            "required_properties": required_by_type[entity["type"]],
            "optional_properties": optional_by_type[entity["type"]],
        }
        node_templates[entity_id] = result
        return copy.deepcopy(result)

    def edge(row: dict[str, str]) -> dict:
        source_node = node(row["from_entity_id"])
        target_node = node(row["to_entity_id"])
        from_id = source_node.get("selected_entity_id")
        to_id = target_node.get("selected_entity_id")
        match_status = (
            "existing"
            if from_id and to_id and (from_id, row["relationship"], to_id) in existing_edges
            else "needs_review"
            if source_node["match_status"] == "possible_duplicate" or target_node["match_status"] == "possible_duplicate"
            else "new"
        )
        return {
            "temp_id": temp_id("e", row["id"]),
            "from_ref": temp_id("n", row["from_entity_id"]),
            "relationship": row["relationship"],
            "to_ref": temp_id("n", row["to_entity_id"]),
            "recommendations": parse_recommendations(row.get("recommendations", "[]")),
            "source": row["source"],
            "evidence": [f"Quan hệ chuẩn hóa {row['id']} từ {SOURCE_KEY}."],
            "confidence": 0.9,
            "match_status": match_status,
            "decision": "pending",
            "validation_issues": [],
        }

    def append_job(kind: str, number: int, total: int, entity_ids: set[str], rows: list[dict[str, str]]) -> None:
        job_id = f"{SOURCE_KEY}-{kind}-{number:04d}"
        existing = repository.get(job_id)
        if existing and existing.get("status") == "applied":
            return
        job = {
            "id": job_id,
            "source_key": SOURCE_KEY,
            "source_label": f"Hà Nội relational · {kind} {number:03d}/{total:03d}",
            "source_url": None,
            "source_content": (
                "Dữ liệu đã được chuẩn hóa từ bộ CSV quan hệ Hà Nội. "
                "Đây chỉ là proposal; mọi node và edge phải được admin duyệt trước khi apply."
            ),
            "status": "needs_review",
            "schema_version": version(schema),
            "ontology_version": version(ontology),
            "dataset_hash": dataset_hash,
            "warnings": [
                "Proposal được tạo bằng rule-based converter, không phải dữ liệu đã nhập.",
                "Node Area/Activity hỗ trợ có thể lặp giữa các batch; hãy Revalidate trước khi duyệt batch tiếp theo.",
            ],
            "nodes": [node(entity_id) for entity_id in sorted(entity_ids)],
            "edges": [edge(row) for row in rows],
            "created_by": 0,
            "created_at": (base_time + timedelta(milliseconds=len(jobs))).isoformat(),
            "applied_at": None,
            "error_message": None,
        }
        job["node_count"] = len(job["nodes"])
        job["edge_count"] = len(job["edges"])
        job["issue_count"] = sum(
            len(item.get("validation_issues", []))
            for item in [*job["nodes"], *job["edges"]]
        )
        jobs.append(job)
        covered_entities.update(entity_ids)
        covered_edges.update(row["id"] for row in rows)

    place_ids = sorted(row["id"] for row in entities if row["type"] in PLACE_TYPES)
    place_id_set = set(place_ids)
    place_batches = chunks(place_ids, batch_size)
    outgoing_by_place: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in relationships:
        if row["from_entity_id"] in place_id_set:
            outgoing_by_place[row["from_entity_id"]].append(row)
    for index, place_batch in enumerate(place_batches, start=1):
        batch_rows = [row for entity_id in place_batch for row in outgoing_by_place.get(str(entity_id), [])]
        endpoint_ids = {str(value) for value in place_batch}
        endpoint_ids.update(row["to_entity_id"] for row in batch_rows)
        append_job("places", index, len(place_batches), endpoint_ids, batch_rows)

    remaining_edges = [row for row in relationships if row["id"] not in covered_edges]
    edge_batches = chunks(remaining_edges, batch_size)
    for index, raw_batch in enumerate(edge_batches, start=1):
        batch = [dict(row) for row in raw_batch]
        endpoint_ids = {
            entity_id
            for row in batch
            for entity_id in (row["from_entity_id"], row["to_entity_id"])
        }
        append_job("relations", index, len(edge_batches), endpoint_ids, batch)

    isolated_ids = sorted(set(entity_by_id) - covered_entities)
    isolated_batches = chunks(isolated_ids, batch_size)
    for index, raw_batch in enumerate(isolated_batches, start=1):
        append_job(
            "isolated",
            index,
            len(isolated_batches),
            {str(value) for value in raw_batch},
            [],
        )

    manifest = {
        "sourceKey": SOURCE_KEY,
        "status": "needs_review",
        "decision": "pending",
        "jobCount": len(jobs),
        "proposalNodeOccurrences": sum(len(job["nodes"]) for job in jobs),
        "uniqueEntityCount": len(entity_by_id),
        "proposalEdgeCount": sum(len(job["edges"]) for job in jobs),
        "uniqueRelationshipCount": len(relationships),
        "batchSize": batch_size,
        "datasetHash": dataset_hash,
    }
    return jobs, manifest


def main() -> None:
    args = parse_args()
    if args.batch_size < 1 or args.batch_size > 80:
        raise ValueError("batch-size phải nằm trong khoảng 1..80 để mỗi job không quá lớn.")
    candidate_dir = args.candidate_dir.resolve()
    dataset = KnowledgeGraphDataset(args.graph_dir.resolve())
    repository = GraphImportRepository(args.repository.resolve())
    jobs, manifest = build_jobs(candidate_dir, dataset, repository, args.batch_size)
    if not args.check_only:
        repository.save_many(jobs)
        (candidate_dir / "pending_import_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
