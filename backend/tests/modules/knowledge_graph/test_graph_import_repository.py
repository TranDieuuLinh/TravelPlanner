"""Tests for GraphImportRepository (PostgreSQL)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.modules.knowledge_graph.repositories import GraphImportRepository


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
    return GraphImportRepository(db_session)


@pytest.fixture
def sample_job():
    return {
        "id": "test-import-001",
        "source_label": "Test Source",
        "source_url": "https://example.com",
        "source_content": "Test content",
        "status": "needs_review",
        "schema_version": "abc123",
        "ontology_version": "def456",
        "dataset_hash": "hash789",
        "warnings": [],
        "node_count": 2,
        "edge_count": 1,
        "issue_count": 0,
        "created_by": 1,
        "created_at": "2026-08-04T10:00:00+00:00",
        "applied_at": None,
        "applied_dataset_hash": None,
        "error_message": None,
    }


class TestGraphImportRepository:
    def test_save_creates_job(self, repo: GraphImportRepository, sample_job: dict) -> None:
        result = repo.save(sample_job)
        assert result["id"] == sample_job["id"]
        assert repo.count() == 1

    def test_save_updates_existing(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        sample_job["status"] = "applied"
        result = repo.save(sample_job)
        assert result["status"] == "applied"
        assert repo.count() == 1

    def test_get_returns_job(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        job = repo.get("test-import-001")
        assert job is not None
        assert job["id"] == "test-import-001"
        assert job["source_label"] == "Test Source"

    def test_get_returns_none_for_missing(self, repo: GraphImportRepository) -> None:
        assert repo.get("nonexistent") is None

    def test_get_meta(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        meta = repo.get_meta("test-import-001")
        assert meta is not None
        assert "source_content" in meta
        assert "schema_version" in meta

    def test_delete_removes_job(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        assert repo.delete("test-import-001") is True
        assert repo.get("test-import-001") is None
        assert repo.count() == 0

    def test_delete_returns_false_for_missing(self, repo: GraphImportRepository) -> None:
        assert repo.delete("nonexistent") is False

    def test_list_pagination(self, repo: GraphImportRepository) -> None:
        for i in range(5):
            job = {
                "id": f"import-{i:03d}",
                "source_label": f"Source {i}",
                "source_content": "",
                "status": "needs_review",
                "schema_version": "v1",
                "ontology_version": "v1",
                "dataset_hash": "hash",
                "warnings": [],
                "created_by": 1,
                "created_at": "2026-08-04T10:00:00+00:00",
            }
            repo.save(job)
        items, total = repo.list(limit=2, offset=0)
        assert len(items) == 2
        assert total == 5
        items, total = repo.list(limit=2, offset=4)
        assert len(items) == 1
        assert total == 5

    def test_list_filter_by_status(self, repo: GraphImportRepository) -> None:
        for i in range(3):
            job = {
                "id": f"import-{i:03d}",
                "source_label": f"Source {i}",
                "source_content": "",
                "status": "needs_review" if i < 2 else "applied",
                "schema_version": "v1",
                "ontology_version": "v1",
                "dataset_hash": "hash",
                "warnings": [],
                "created_by": 1,
                "created_at": "2026-08-04T10:00:00+00:00",
            }
            repo.save(job)
        items, total = repo.list(status="needs_review")
        assert total == 2
        items, total = repo.list(status="applied")
        assert total == 1

    def test_list_filter_by_search(self, repo: GraphImportRepository) -> None:
        for label in ["Hanoi Travel Guide", "Saigon Restaurant", "HCMC Museum"]:
            job = {
                "id": label.lower().replace(" ", "-"),
                "source_label": label,
                "source_content": "",
                "status": "needs_review",
                "schema_version": "v1",
                "ontology_version": "v1",
                "dataset_hash": "hash",
                "warnings": [],
                "created_by": 1,
                "created_at": "2026-08-04T10:00:00+00:00",
            }
            repo.save(job)
        items, total = repo.list(search="hanoi")
        assert total == 1
        assert items[0]["source_label"] == "Hanoi Travel Guide"

    def test_count(self, repo: GraphImportRepository) -> None:
        assert repo.count() == 0
        for i in range(3):
            job = {
                "id": f"import-{i:03d}",
                "source_label": f"Source {i}",
                "source_content": "",
                "status": "needs_review",
                "schema_version": "v1",
                "ontology_version": "v1",
                "dataset_hash": "hash",
                "warnings": [],
                "created_by": 1,
                "created_at": "2026-08-04T10:00:00+00:00",
            }
            repo.save(job)
        assert repo.count() == 3


class TestGraphImportRepositoryNodes:
    def test_save_and_list_nodes(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        nodes = [
            {
                "temp_id": "n_001",
                "entity_id": "place_001",
                "type": "Place",
                "canonical_name": "Hoan Kiem Lake",
                "aliases": [],
                "properties": {},
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "match_candidates": [],
                "decision": "pending",
                "validation_issues": [],
                "required_properties": [],
                "optional_properties": [],
            },
            {
                "temp_id": "n_002",
                "entity_id": "city_001",
                "type": "City",
                "canonical_name": "Hanoi",
                "aliases": [],
                "properties": {},
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "match_candidates": [],
                "decision": "pending",
                "validation_issues": [],
                "required_properties": [],
                "optional_properties": [],
            },
        ]
        repo.save_nodes("test-import-001", nodes)
        items, total = repo.list_nodes("test-import-001")
        assert total == 2
        assert len(items) == 2
        assert items[0]["temp_id"] == "n_001"

    def test_list_nodes_pagination(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        nodes = [
            {
                "temp_id": f"n_{i:03d}",
                "entity_id": f"place_{i:03d}",
                "type": "Place",
                "canonical_name": f"Place {i}",
                "aliases": [],
                "properties": {},
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "match_candidates": [],
                "decision": "pending",
                "validation_issues": [],
                "required_properties": [],
                "optional_properties": [],
            }
            for i in range(10)
        ]
        repo.save_nodes("test-import-001", nodes)
        items, total = repo.list_nodes("test-import-001", limit=3, offset=0)
        assert len(items) == 3
        assert total == 10
        items, total = repo.list_nodes("test-import-001", limit=3, offset=9)
        assert len(items) == 1
        assert total == 10

    def test_update_node(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        nodes = [
            {
                "temp_id": "n_001",
                "entity_id": "place_001",
                "type": "Place",
                "canonical_name": "Hoan Kiem Lake",
                "aliases": [],
                "properties": {},
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "match_candidates": [],
                "decision": "pending",
                "validation_issues": [],
                "required_properties": [],
                "optional_properties": [],
            }
        ]
        repo.save_nodes("test-import-001", nodes)
        updated = repo.update_node("test-import-001", "n_001", {"decision": "approve_create"})
        assert updated is not None
        assert updated["decision"] == "approve_create"

    def test_delete_node(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        nodes = [
            {
                "temp_id": "n_001",
                "entity_id": "place_001",
                "type": "Place",
                "canonical_name": "Hoan Kiem Lake",
                "aliases": [],
                "properties": {},
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "match_candidates": [],
                "decision": "pending",
                "validation_issues": [],
                "required_properties": [],
                "optional_properties": [],
            }
        ]
        repo.save_nodes("test-import-001", nodes)
        assert repo.delete_node("test-import-001", "n_001") is True
        items, total = repo.list_nodes("test-import-001")
        assert total == 0


class TestGraphImportRepositoryEdges:
    def test_save_and_list_edges(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        edges = [
            {
                "temp_id": "e_001",
                "from_ref": "n_001",
                "relationship": "LOCATED_IN",
                "to_ref": "n_002",
                "recommendations": [],
                "source": "test",
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "decision": "pending",
                "validation_issues": [],
            }
        ]
        repo.save_edges("test-import-001", edges)
        items, total = repo.list_edges("test-import-001")
        assert total == 1
        assert len(items) == 1
        assert items[0]["relationship"] == "LOCATED_IN"

    def test_update_edge(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        edges = [
            {
                "temp_id": "e_001",
                "from_ref": "n_001",
                "relationship": "LOCATED_IN",
                "to_ref": "n_002",
                "recommendations": [],
                "source": "test",
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "decision": "pending",
                "validation_issues": [],
            }
        ]
        repo.save_edges("test-import-001", edges)
        updated = repo.update_edge("test-import-001", "e_001", {"decision": "approve_create"})
        assert updated is not None
        assert updated["decision"] == "approve_create"

    def test_delete_edge(self, repo: GraphImportRepository, sample_job: dict) -> None:
        repo.save(sample_job)
        edges = [
            {
                "temp_id": "e_001",
                "from_ref": "n_001",
                "relationship": "LOCATED_IN",
                "to_ref": "n_002",
                "recommendations": [],
                "source": "test",
                "evidence": [],
                "confidence": 0.9,
                "match_status": "new",
                "decision": "pending",
                "validation_issues": [],
            }
        ]
        repo.save_edges("test-import-001", edges)
        assert repo.delete_edge("test-import-001", "e_001") is True
        items, total = repo.list_edges("test-import-001")
        assert total == 0
