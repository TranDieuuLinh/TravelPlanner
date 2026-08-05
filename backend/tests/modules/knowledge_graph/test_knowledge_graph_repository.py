"""Tests for KnowledgeGraphRepository."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.modules.knowledge_graph.repositories import KnowledgeGraphRepository


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def repo(db_session: Session):
    return KnowledgeGraphRepository(db_session)


class TestKnowledgeGraphRepositoryEntities:
    def test_stats_empty(self, repo: KnowledgeGraphRepository) -> None:
        stats = repo.stats()
        assert stats["entity_count"] == 0
        assert stats["alias_count"] == 0
        assert stats["relationship_count"] == 0

    def test_upsert_entity_creates(self, repo: KnowledgeGraphRepository) -> None:
        entity = repo.upsert_entity(
            entity_id="place_001",
            canonical_name="Hoan Kiem Lake",
            entity_type="Place",
            status="verified",
        )
        assert entity.id == "place_001"
        assert entity.canonical_name == "Hoan Kiem Lake"
        assert entity.entity_type == "Place"
        assert entity.status == "verified"
        assert entity.normalized_name == "hoan kiem lake"

    def test_upsert_entity_updates(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        entity = repo.upsert_entity("place_001", "Hoan Kiem Lake Updated", "TravelPlace", status="draft")
        assert entity.canonical_name == "Hoan Kiem Lake Updated"
        assert entity.entity_type == "TravelPlace"
        assert entity.status == "draft"

    def test_get_entity(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        entity = repo.get_entity("place_001")
        assert entity is not None
        assert entity.id == "place_001"

    def test_get_entity_not_found(self, repo: KnowledgeGraphRepository) -> None:
        entity = repo.get_entity("nonexistent")
        assert entity is None

    def test_delete_entity(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        assert repo.delete_entity("place_001") is True
        assert repo.get_entity("place_001") is None

    def test_delete_entity_not_found(self, repo: KnowledgeGraphRepository) -> None:
        assert repo.delete_entity("nonexistent") is False

    def test_list_entities_pagination(self, repo: KnowledgeGraphRepository) -> None:
        for i in range(10):
            repo.upsert_entity(f"place_{i:03d}", f"Place {i}", "Place")
        entities, total = repo.list_entities(limit=3, offset=0)
        assert len(entities) == 3
        assert total == 10
        entities, total = repo.list_entities(limit=3, offset=6)
        assert len(entities) == 3
        assert total == 10

    def test_list_entities_filter_by_type(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Place 1", "Place")
        repo.upsert_entity("city_001", "City 1", "City")
        entities, total = repo.list_entities(entity_type="Place")
        assert len(entities) == 1
        assert total == 1
        assert entities[0].entity_type == "Place"

    def test_list_entities_filter_by_status(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Place 1", "Place", status="verified")
        repo.upsert_entity("place_002", "Place 2", "Place", status="draft")
        entities, total = repo.list_entities(status="verified")
        assert len(entities) == 1
        assert total == 1
        assert entities[0].status == "verified"

    def test_list_entities_search(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("place_002", "West Lake", "Place")
        entities, total = repo.list_entities(search="hoan")
        assert len(entities) == 1
        assert total == 1
        assert entities[0].canonical_name == "Hoan Kiem Lake"


class TestKnowledgeGraphRepositoryAliases:
    def test_upsert_alias(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        alias = repo.upsert_alias("place_001", "Hồ Hoàn Kiếm", language="vi")
        assert alias.entity_id == "place_001"
        assert alias.alias == "Hồ Hoàn Kiếm"
        assert alias.normalized_alias == "ho hoan kiem"
        assert alias.language == "vi"

    def test_get_aliases_for_entity(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_alias("place_001", "Hồ Hoàn Kiếm")
        repo.upsert_alias("place_001", "Hoan Kiem")
        aliases = repo.get_aliases_for_entity("place_001")
        assert len(aliases) == 2

    def test_delete_alias(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        alias = repo.upsert_alias("place_001", "Hồ Hoàn Kiếm")
        assert repo.delete_alias(alias.id) is True
        assert len(repo.get_aliases_for_entity("place_001")) == 0

    def test_find_exact_alias_match(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_alias("place_001", "Hồ Hoàn Kiếm")
        alias = repo.find_exact_alias_match("ho hoan kiem")
        assert alias is not None
        assert alias.alias == "Hồ Hoàn Kiếm"

    def test_find_exact_alias_match_not_found(self, repo: KnowledgeGraphRepository) -> None:
        assert repo.find_exact_alias_match("nonexistent") is None


class TestKnowledgeGraphRepositoryProperties:
    def test_upsert_property(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        prop = repo.upsert_property("place_001", "address", "Hanoi, Vietnam", source="test")
        assert prop.entity_id == "place_001"
        assert prop.key == "address"
        assert prop.value == "Hanoi, Vietnam"
        assert prop.source == "test"

    def test_get_properties_for_entity(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_property("place_001", "address", "Hanoi")
        repo.upsert_property("place_001", "latitude", "21.0285")
        props = repo.get_properties_for_entity("place_001")
        assert len(props) == 2
        assert {p.key for p in props} == {"address", "latitude"}

    def test_delete_property(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        prop = repo.upsert_property("place_001", "address", "Hanoi")
        assert repo.delete_property(prop.id) is True
        assert len(repo.get_properties_for_entity("place_001")) == 0


class TestKnowledgeGraphRepositoryRelationships:
    def test_upsert_relationship(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("city_001", "Hanoi", "City")
        rel = repo.upsert_relationship("place_001", "LOCATED_IN", "city_001", source="test")
        assert rel.from_entity_id == "place_001"
        assert rel.relationship == "LOCATED_IN"
        assert rel.to_entity_id == "city_001"

    def test_list_relationships(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("city_001", "Hanoi", "City")
        repo.upsert_relationship("place_001", "LOCATED_IN", "city_001")
        rels, total = repo.list_relationships(limit=10, offset=0)
        assert len(rels) == 1
        assert total == 1

    def test_list_relationships_filter(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("city_001", "Hanoi", "City")
        repo.upsert_entity("place_002", "West Lake", "Place")
        repo.upsert_relationship("place_001", "LOCATED_IN", "city_001")
        repo.upsert_relationship("place_002", "NEAR", "place_001")
        rels, total = repo.list_relationships(relationship="LOCATED_IN")
        assert len(rels) == 1
        assert total == 1
        assert rels[0].relationship == "LOCATED_IN"

    def test_delete_relationship(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("city_001", "Hanoi", "City")
        rel = repo.upsert_relationship("place_001", "LOCATED_IN", "city_001")
        assert repo.delete_relationship(rel.id) is True
        rels, total = repo.list_relationships()
        assert total == 0


class TestKnowledgeGraphRepositoryMatching:
    def test_find_exact_name_match(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        entity = repo.find_exact_name_match("hoan kiem lake")
        assert entity is not None
        assert entity.id == "place_001"

    def test_find_exact_name_match_not_found(self, repo: KnowledgeGraphRepository) -> None:
        assert repo.find_exact_name_match("nonexistent") is None

    def test_find_fuzzy_entity_candidates(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("place_002", "Hoan Kiem District", "Area")
        repo.upsert_entity("city_001", "Hanoi", "City")
        candidates = repo.find_fuzzy_entity_candidates("hoan kiem", limit=5)
        assert len(candidates) == 2
        assert {c.id for c in candidates} == {"place_001", "place_002"}

    def test_fuzzy_candidates_respects_limit(self, repo: KnowledgeGraphRepository) -> None:
        for i in range(10):
            repo.upsert_entity(f"place_{i:03d}", f"Hoan Kiem Location {i}", "Place")
        candidates = repo.find_fuzzy_entity_candidates("hoan kiem", limit=3)
        assert len(candidates) == 3


class TestKnowledgeGraphRepositoryEntityDetail:
    def test_get_entity_detail(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_alias("place_001", "Hồ Hoàn Kiếm")
        repo.upsert_property("place_001", "address", "Hanoi")
        detail = repo.get_entity_detail("place_001", alias_limit=10, property_limit=10)
        assert detail is not None
        assert detail["entity"].id == "place_001"
        assert len(detail["aliases"]) == 1
        assert len(detail["properties"]) == 1
        assert detail["alias_total"] == 1
        assert detail["property_total"] == 1

    def test_get_entity_detail_not_found(self, repo: KnowledgeGraphRepository) -> None:
        detail = repo.get_entity_detail("nonexistent")
        assert detail is None


class TestKnowledgeGraphRepositoryStats:
    def test_stats_after_operations(self, repo: KnowledgeGraphRepository) -> None:
        repo.upsert_entity("place_001", "Hoan Kiem Lake", "Place")
        repo.upsert_entity("city_001", "Hanoi", "City")
        repo.upsert_alias("place_001", "Hồ Hoàn Kiếm")
        repo.upsert_alias("place_001", "Hoan Kiem")
        repo.upsert_property("place_001", "address", "Hanoi")
        repo.upsert_relationship("place_001", "LOCATED_IN", "city_001")

        stats = repo.stats()
        assert stats["entity_count"] == 2
        assert stats["alias_count"] == 2
        assert stats["relationship_count"] == 1
