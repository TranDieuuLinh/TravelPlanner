import asyncio
from datetime import datetime, timezone

from app.modules.knowledge_graph.contract import EntityCreate, EntityUpdate, RelationshipUpsert
from app.modules.knowledge_graph.ontology import ontology_payload
from app.modules.knowledge_graph.service import KnowledgeGraphError, KnowledgeGraphService


class FakeStore:
    def __init__(self):
        self.entity = {
            "id": "hanoi",
            "canonical_name": "Hanoi",
            "normalized_name": "hanoi",
            "entity_type": "City",
            "status": "active",
            "review_count": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "aliases": [],
            "properties": [],
            "relationships": [],
            "alias_total": 0,
            "property_total": 0,
            "relationship_total": 0,
            "alias_has_more": False,
            "property_has_more": False,
            "relationship_has_more": False,
        }

    async def get_entity(self, entity_id: str, **_):
        return self.entity if entity_id == self.entity["id"] else None

    async def update_entity(self, entity_id: str, **payload):
        if entity_id != self.entity["id"]:
            return None
        self.entity.update({key: value for key, value in payload.items() if value is not None})
        return self.entity

    async def delete_entity(self, entity_id: str):
        return entity_id == self.entity["id"]


def test_update_entity_uses_public_contract() -> None:
    store = FakeStore()
    service = KnowledgeGraphService(store)  # type: ignore[arg-type]

    result = asyncio.run(service.update_entity("hanoi", EntityUpdate(canonical_name="Hà Nội")))

    assert result["canonical_name"] == "Hà Nội"


def test_missing_entity_returns_domain_error() -> None:
    service = KnowledgeGraphService(FakeStore())  # type: ignore[arg-type]

    try:
        asyncio.run(service.entity("missing"))
    except KnowledgeGraphError as error:
        assert error.status_code == 404
    else:
        raise AssertionError("missing entity should raise KnowledgeGraphError")



def test_entity_create_accepts_camel_case() -> None:
    payload = EntityCreate.model_validate(
        {"entityId": "hanoi", "canonicalName": "Hanoi", "entityType": "City"}
    )

    assert payload.entity_id == "hanoi"
    assert payload.status == "draft"


def test_ontology_has_frontend_shape() -> None:
    payload = ontology_payload()

    assert "ADM1" in payload["nodeTypes"]
    assert "time_windows" in payload["propertyKeys"]
    assert "Located_In" in payload["relationshipTypes"]
    assert payload["nodeTypeProperties"]["Restaurant"]["requiredProperties"] == [
        "id",
        "name",
        "type",
        "latitude",
        "longitude",
    ]
    assert "time_windows" in payload["nodeTypeProperties"]["ActivityItem"]["optionalProperties"]


class RelationshipStore:
    def __init__(self) -> None:
        self.added: tuple[object, ...] | None = None

    async def add_relationship(self, *args):
        self.added = args
        return {"id": "source"}

    async def get_entity(self, entity_id: str, **_):
        return {"id": entity_id}


def test_relationship_contract_allows_custom_source_entity() -> None:
    store = RelationshipStore()
    service = KnowledgeGraphService(store)  # type: ignore[arg-type]
    payload = RelationshipUpsert.model_validate(
        {"fromEntityId": "source", "relationship": "located_in", "toEntityId": "destination"}
    )

    asyncio.run(service.relationship("context", payload))

    assert store.added is not None
    assert store.added[0] == "source"
