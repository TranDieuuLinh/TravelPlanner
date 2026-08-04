import csv
import hashlib
import io
import json
import re
import threading
from pathlib import Path

import yaml

from app.core.config import BACKEND_ROOT

GRAPH_DIRECTORY = BACKEND_ROOT.parent / "knowledge-graph-real-v2"
GRAPH_FILES = (
    "aliases.csv",
    "entities.csv",
    "ontology.yaml",
    "properties.csv",
    "relationships.csv",
    "schema.yaml",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return []
    return [dict(row) for row in csv.DictReader(io.StringIO(content))]


def _write_csv(fieldnames: list[str], rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


class KnowledgeGraphDataset:
    _lock = threading.RLock()

    def __init__(self, directory: Path = GRAPH_DIRECTORY) -> None:
        self.directory = directory

    def hash(self) -> str:
        digest = hashlib.sha256()
        for name in GRAPH_FILES:
            digest.update(name.encode())
            digest.update((self.directory / name).read_bytes())
        return digest.hexdigest()

    def raw_contract(self) -> tuple[str, str]:
        return (
            (self.directory / "schema.yaml").read_text(encoding="utf-8"),
            (self.directory / "ontology.yaml").read_text(encoding="utf-8"),
        )

    def entities(self) -> list[dict[str, str]]:
        return _read_csv(self.directory / "entities.csv")

    def aliases(self) -> list[dict[str, str]]:
        return _read_csv(self.directory / "aliases.csv")

    def relationships(self) -> list[dict[str, str]]:
        return _read_csv(self.directory / "relationships.csv")

    def allowed_nodes(self) -> set[str]:
        schema = (self.directory / "schema.yaml").read_text(encoding="utf-8")
        return self._yaml_list(schema, "nodes")

    def allowed_relationships(self) -> set[str]:
        schema = (self.directory / "schema.yaml").read_text(encoding="utf-8")
        return self._yaml_list(schema, "relationships")

    def next_entity_id(self, type_prefix: str) -> str:
        """Generate next entity ID for a given type prefix (e.g., 'area' -> 'area_002')."""
        entities = self.entities()
        prefix = f"{type_prefix}_"
        used_numbers: set[int] = set()
        for row in entities:
            entity_id = row.get("id", "")
            if entity_id.startswith(prefix):
                suffix = entity_id[len(prefix):]
                try:
                    used_numbers.add(int(suffix))
                except ValueError:
                    pass
        next_num = max(used_numbers, default=0) + 1
        return f"{type_prefix}_{next_num:03d}"

    def entity_type_prefix(self, node_type: str) -> str:
        """Map node type to ID prefix."""
        prefix_map = {
            "Area": "area",
            "City": "city",
            "District": "district",
            "TravelPlace": "place",
            "Restaurant": "restaurant",
            "DrinkDessert": "drink",
            "Accommodation": "hotel",
            "Activity": "activity",
        }
        return prefix_map.get(node_type, node_type.lower())

    def node_type_definitions(self) -> dict[str, dict[str, object]]:
        content = (self.directory / "schema.yaml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(content) or {}
        definitions = parsed.get("node_type_definitions", {})
        return definitions if isinstance(definitions, dict) else {}

    def type_lineage(self, node_type: str) -> set[str]:
        definitions = self.node_type_definitions()
        lineage: set[str] = set()
        current = node_type
        while current and current not in lineage:
            lineage.add(current)
            definition = definitions.get(current, {})
            extends = None
            if isinstance(definition, dict):
                extends = definition.get("extends") or definition.get("inherits")
            elif isinstance(definition, str):
                extends = definition
            current = str(extends) if extends else ""
        return lineage

    def type_matches(self, node_type: str, expected_types: set[str]) -> bool:
        return not expected_types or bool(self.type_lineage(node_type) & expected_types)

    def required_properties(self, node_type: str) -> set[str]:
        definitions = self.node_type_definitions()
        required: set[str] = set()
        for current in self.type_lineage(node_type):
            definition = definitions.get(current, {})
            values = definition.get("required_properties", []) if isinstance(definition, dict) else []
            if isinstance(values, list):
                required.update(str(value) for value in values)
        return required

    def optional_properties(self, node_type: str) -> set[str]:
        definitions = self.node_type_definitions()
        optional: set[str] = set()
        for current in self.type_lineage(node_type):
            definition = definitions.get(current, {})
            values = definition.get("optional_properties", []) if isinstance(definition, dict) else []
            if isinstance(values, list):
                optional.update(str(value) for value in values)
        return optional

    def property_definitions(self) -> dict[str, dict[str, str]]:
        """Get all property definitions from schema.yaml."""
        content = (self.directory / "schema.yaml").read_text(encoding="utf-8")
        parsed = yaml.safe_load(content) or {}
        return parsed.get("property_definitions", {})

    def relationship_contracts(self) -> dict[str, tuple[set[str], set[str]]]:
        content = (self.directory / "ontology.yaml").read_text(encoding="utf-8")
        contracts: dict[str, tuple[set[str], set[str]]] = {}
        for block in re.split(r"\r?\n\s*\r?\n", content.strip()):
            lines = block.splitlines()
            if not lines:
                continue
            name = lines[0].rstrip(":").strip()
            fields = {}
            for line in lines[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    fields[key.strip()] = value.strip()
            if "from" in fields or "to" in fields:
                contracts[name] = (
                    {value.strip() for value in fields.get("from", "").split("|") if value.strip()},
                    {value.strip() for value in fields.get("to", "").split("|") if value.strip()},
                )
        return contracts

    def apply(
        self,
        *,
        nodes: list[dict[str, object]],
        edges: list[dict[str, object]],
        expected_hash: str,
    ) -> str:
        with self._lock:
            if self.hash() != expected_hash:
                raise ValueError("DATASET_VERSION_CONFLICT")
            entity_rows = self.entities()
            alias_rows = self.aliases()
            property_rows = _read_csv(self.directory / "properties.csv")
            relationship_rows = self.relationships()
            for index, row in enumerate(relationship_rows):
                if not row.get("id"):
                    raw_key = "|".join([
                        row.get("from_entity_id", ""),
                        row.get("relationship", ""),
                        row.get("to_entity_id", ""),
                    ])
                    row["id"] = f"edge_{hashlib.sha256(raw_key.encode()).hexdigest()[:16]}_{index}"
                row.setdefault("recommendations", "[]")
            entity_ids = {row.get("id", "") for row in entity_rows}
            alias_keys = {(row.get("entity_id", ""), row.get("alias", "")) for row in alias_rows}
            property_by_key = {
                (row.get("entity_id", ""), row.get("key", "")): row
                for row in property_rows
            }
            edge_by_key = {
                (row.get("from_entity_id", ""), row.get("relationship", ""), row.get("to_entity_id", "")): row
                for row in relationship_rows
            }

            for node in nodes:
                entity_id = str(node["entity_id"])
                if node["decision"] == "approve_create" and entity_id not in entity_ids:
                    entity_rows.append({
                        "id": entity_id,
                        "name": str(node["canonical_name"]),
                        "type": str(node["type"]),
                        "status": "draft",
                    })
                    entity_ids.add(entity_id)
                target_id = str(node.get("selected_entity_id") or entity_id)
                if node["decision"] in {"approve_create", "approve_existing"}:
                    for alias in [str(node["canonical_name"]), *[str(value) for value in node.get("aliases", [])]]:
                        key = (target_id, alias)
                        if alias and key not in alias_keys:
                            alias_rows.append({"entity_id": target_id, "alias": alias})
                            alias_keys.add(key)
                    for property_key, property_value in dict(node.get("properties", {})).items():
                        key = (target_id, str(property_key))
                        row = property_by_key.get(key)
                        next_value = str(property_value)
                        next_source = str(node.get("property_source", ""))
                        if row:
                            row["value"] = next_value
                            row["source"] = next_source
                        else:
                            row = {
                                "entity_id": target_id,
                                "key": key[1],
                                "value": next_value,
                                "source": next_source,
                            }
                            property_rows.append(row)
                            property_by_key[key] = row

            for edge in edges:
                if edge["decision"] not in {"approve_create", "approve_existing"}:
                    continue
                key = (str(edge["from_id"]), str(edge["relationship"]), str(edge["to_id"]))
                existing = edge_by_key.get(key)
                source = str(edge["source"])
                recommendations = edge.get("recommendations", [])
                if existing:
                    sources = [item.strip() for item in existing.get("source", "").split(" | ") if item.strip()]
                    if source not in sources:
                        existing["source"] = " | ".join([*sources, source])
                    if recommendations:
                        existing["recommendations"] = json.dumps(recommendations, ensure_ascii=False, separators=(",", ":"))
                else:
                    row = {
                        "id": f"edge_{hashlib.sha256('|'.join(key).encode()).hexdigest()[:16]}",
                        "from_entity_id": key[0],
                        "relationship": key[1],
                        "to_entity_id": key[2],
                        "recommendations": json.dumps(recommendations, ensure_ascii=False, separators=(",", ":")),
                        "source": source,
                    }
                    relationship_rows.append(row)
                    edge_by_key[key] = row

            updates = {
                "entities.csv": _write_csv(["id", "name", "type", "status"], entity_rows),
                "aliases.csv": _write_csv(["entity_id", "alias"], alias_rows),
                "properties.csv": _write_csv(
                    ["entity_id", "key", "value", "source"], property_rows
                ),
                "relationships.csv": _write_csv(
                    ["id", "from_entity_id", "relationship", "to_entity_id", "recommendations", "source"],
                    relationship_rows,
                ),
            }
            temporary: list[tuple[Path, Path]] = []
            for name, content in updates.items():
                target = self.directory / name
                temp = target.with_suffix(f"{target.suffix}.tmp")
                temp.write_text(content, encoding="utf-8")
                temporary.append((temp, target))
            for temp, target in temporary:
                temp.replace(target)
            return self.hash()

    @staticmethod
    def _yaml_list(content: str, section: str) -> set[str]:
        match = re.search(
            rf"(?ms)^{re.escape(section)}:\s*\n(?P<body>(?:\s+-[^\n]+\n?)+)",
            content,
        )
        if not match:
            return set()
        return {
            line.strip().removeprefix("-").strip()
            for line in match.group("body").splitlines()
            if line.strip().startswith("-")
        }
