import asyncio
import csv
import io
import json
from pathlib import Path

from app.integrations.llm.base import LLMClient
from app.modules.knowledge_graph.dataset import KnowledgeGraphDataset
from app.modules.knowledge_graph.repository import GraphImportRepository
from app.modules.knowledge_graph.schema import (
    GraphImportCreate,
    ProposedNodeRead,
    ProposedEdgeUpdate,
    ProposedNodeUpdate,
)
from app.modules.knowledge_graph.service import KnowledgeGraphImportService


class FakeGraphLLM(LLMClient):
    async def generate_profile_plan(self, prompt: str) -> str:
        return "{}"

    async def generate_json(self, system_prompt: str, user_payload: str) -> str:
        assert "NEVER invent facts" in system_prompt
        assert "responseContract" in json.loads(user_payload)
        return self.output

    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        assert "NEVER invent facts" in system_prompt
        assert response_schema["type"] == "object"
        return self.output

    output = json.dumps(
        {
            "nodes": [
                {
                    "tempId": "n_lake",
                    "entityId": "place_lake_suggestion",
                    "type": "Place",
                    "canonicalName": "Hoan Kiem Lake",
                    "aliases": ["Hồ Hoàn Kiếm"],
                    "properties": {},
                    "evidence": ["Hoan Kiem Lake is in Hanoi"],
                    "confidence": 0.96,
                },
                {
                    "tempId": "n_city",
                    "entityId": "city_hanoi",
                    "type": "City",
                    "canonicalName": "Hà Nội",
                    "aliases": ["Hanoi"],
                    "properties": {},
                    "evidence": ["in Hanoi"],
                    "confidence": 0.92,
                },
            ],
            "edges": [
                {
                    "tempId": "e_location",
                    "fromRef": "n_lake",
                    "relationship": "LOCATED_IN",
                    "toRef": "n_city",
                    "source": "test-source",
                    "evidence": ["Hoan Kiem Lake is in Hanoi"],
                    "confidence": 0.95,
                }
            ],
            "warnings": [],
        },
        ensure_ascii=False,
    )


def _dataset(directory: Path) -> KnowledgeGraphDataset:
    directory.mkdir()
    (directory / "entities.csv").write_text(
        "id,name,type,status\nplace_001,Hoan Kiem Lake,Place,verified\n",
        encoding="utf-8",
    )
    (directory / "aliases.csv").write_text(
        "entity_id,alias\nplace_001,Hoan Kiem Lake\n",
        encoding="utf-8",
    )
    (directory / "relationships.csv").write_text(
        "from_entity_id,relationship,to_entity_id,source\n",
        encoding="utf-8",
    )
    (directory / "properties.csv").write_text("", encoding="utf-8")
    (directory / "schema.yaml").write_text(
        """nodes:
  - Place
  - City

relationships:
  - LOCATED_IN

property_definitions:
  description: { type: string }

node_type_definitions:
  Entity:
    abstract: true
    required_properties: [description]

constraints:
  Place.id: unique
""",
        encoding="utf-8",
    )
    (directory / "ontology.yaml").write_text(
        "Place:\n  description: Điểm tham quan\n\nCity:\n  description: Thành phố\n\nLOCATED_IN:\n  from: Place\n  to: City\n",
        encoding="utf-8",
    )
    return KnowledgeGraphDataset(directory)


def test_import_matches_existing_node_and_applies_approved_graph(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "graph")
    service = KnowledgeGraphImportService(
        GraphImportRepository(tmp_path / "imports.json"),
        dataset,
        FakeGraphLLM(),
    )

    created = asyncio.run(
        service.create(
            GraphImportCreate(
                sourceLabel="Test source",
                content="Hoan Kiem Lake is in Hanoi city.",
            ),
            user_id=1,
        )
    )

    assert created["status"] == "needs_review"
    assert created["nodes"][0]["match_status"] == "existing"
    assert created["nodes"][0]["selected_entity_id"] == "place_001"
    assert created["nodes"][1]["match_status"] == "new"

    service.update_node(
        created["id"],
        "n_lake",
        ProposedNodeUpdate(
            entityId="place_lake_suggestion",
            type="Place",
            canonicalName="Hoan Kiem Lake",
            aliases=["Hồ Hoàn Kiếm"],
            properties={},
            selectedEntityId="place_001",
            decision="approve_existing",
        ),
    )
    service.update_node(
        created["id"],
        "n_city",
        ProposedNodeUpdate(
            entityId="city_hanoi",
                type="City",
                canonicalName="Hà Nội",
                aliases=["Hanoi"],
                properties={"special_experience": '[{"intent":"visit","priority":"must"}]'},
            decision="approve_create",
        ),
    )
    service.update_edge(
        created["id"],
        "e_location",
            ProposedEdgeUpdate(
                fromRef="n_lake",
                relationship="LOCATED_IN",
                toRef="n_city",
                recommendations=[{
                    "intent": "visit",
                    "priority": "must",
                    "reason": "Test recommendation",
                }],
                source="test-source",
            decision="approve_create",
        ),
    )

    applied = service.apply(created["id"])

    assert applied["status"] == "applied"
    entities = list(csv.DictReader(io.StringIO((dataset.directory / "entities.csv").read_text(encoding="utf-8"))))
    relationships = list(csv.DictReader(io.StringIO((dataset.directory / "relationships.csv").read_text(encoding="utf-8"))))
    properties = list(csv.DictReader(io.StringIO((dataset.directory / "properties.csv").read_text(encoding="utf-8"))))
    assert {row["id"] for row in entities} == {"place_001", "city_hanoi"}
    assert relationships == [
        {
            "id": "edge_d1facb98067bb39e",
            "from_entity_id": "place_001",
            "relationship": "LOCATED_IN",
            "to_entity_id": "city_hanoi",
            "recommendations": '[{"intent":"visit","priority":"must","reason":"Test recommendation"}]',
            "source": "test-source",
        }
    ]
    assert properties == [{
        "entity_id": "city_hanoi",
        "key": "special_experience",
        "value": '[{"intent":"visit","priority":"must"}]',
        "source": "Test source",
    }]


def test_dataset_resolves_parent_types_and_inherited_required_properties(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "graph")
    (dataset.directory / "schema.yaml").write_text(
        """nodes:
  - TravelPlace
  - Activity

relationships:
  - OFFERS_ACTIVITY

property_definitions:
  description: { type: string }
  address: { type: string }
  latitude: { type: number }
  longitude: { type: number }
  activity_category: { type: string }
  special_experience: { type: json_array }

node_type_definitions:
  Entity:
    abstract: true
    optional_properties: [special_experience]
  Place:
    abstract: true
    extends: Entity
    required_properties: [address, latitude, longitude]
  TravelPlace:
    extends: Place
  Activity:
    extends: Entity
    required_properties: [activity_category]
""",
        encoding="utf-8",
    )

    assert dataset.type_matches("TravelPlace", {"Place"})
    assert dataset.type_matches("Activity", {"Entity"})
    assert not dataset.type_matches("Activity", {"Place"})
    assert dataset.required_properties("TravelPlace") == {"address", "latitude", "longitude"}
    assert dataset.required_properties("Activity") == {"activity_category"}


def test_proposed_node_response_exposes_schema_property_fields() -> None:
    node = ProposedNodeRead.model_validate({
        "temp_id": "n_area",
        "entity_id": "area_009",
        "type": "Area",
        "canonical_name": "Thanh Liệt",
        "aliases": [],
        "properties": {"description": "Khu vực Thanh Liệt"},
        "evidence": ["Bản ghi chuẩn hóa"],
        "confidence": 0.9,
        "match_status": "new",
        "match_candidates": [],
        "required_properties": ["description"],
        "optional_properties": ["administrative_level", "latitude", "longitude"],
    })

    payload = node.model_dump(by_alias=True)

    assert payload["requiredProperties"] == ["description"]
    assert payload["optionalProperties"] == [
        "administrative_level",
        "latitude",
        "longitude",
    ]


def test_revalidate_refreshes_hash_and_returns_all_decisions_to_pending(tmp_path: Path) -> None:
    dataset = _dataset(tmp_path / "graph")
    repository = GraphImportRepository(tmp_path / "imports.json")
    service = KnowledgeGraphImportService(repository, dataset, FakeGraphLLM())
    created = asyncio.run(
        service.create(
            GraphImportCreate(
                sourceLabel="Test source",
                content="Hoan Kiem Lake is in Hanoi city.",
            ),
            user_id=1,
        )
    )
    service.update_node(
        created["id"],
        "n_lake",
        ProposedNodeUpdate(
            entityId="place_lake_suggestion",
            type="Place",
            canonicalName="Hoan Kiem Lake",
            aliases=["Hồ Hoàn Kiếm"],
            properties={},
            selectedEntityId="place_001",
            decision="approve_existing",
        ),
    )
    previous_hash = created["dataset_hash"]
    (dataset.directory / "aliases.csv").write_text(
        "entity_id,alias\nplace_001,Hoan Kiem Lake\nplace_001,Hồ Gươm\n",
        encoding="utf-8",
    )

    refreshed = service.revalidate(created["id"])

    assert refreshed["dataset_hash"] != previous_hash
    assert {node["decision"] for node in refreshed["nodes"]} == {"pending"}
    assert {edge["decision"] for edge in refreshed["edges"]} == {"pending"}
    assert repository.list()[0][0]["node_count"] == 2
