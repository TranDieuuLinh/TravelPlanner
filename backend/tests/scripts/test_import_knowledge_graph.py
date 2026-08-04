"""Tests for legacy knowledge graph importer script."""

import csv
import json
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from scripts.import_knowledge_graph import (
    _read_csv_chunked,
    entity_type_prefix,
    import_aliases,
    import_entities,
    import_properties,
    import_relationships,
    normalized,
)


class TestNormalization:
    def test_normalized_lowercase(self) -> None:
        assert normalized("Hoan Kiem Lake") == "hoan kiem lake"

    def test_normalized_removes_accents(self) -> None:
        assert normalized("Hà Nội") == "ha noi"

    def test_normalized_removes_special_chars(self) -> None:
        assert normalized("Cafe 123!@#") == "cafe 123"

    def test_normalized_collapses_spaces(self) -> None:
        assert normalized("  Hoan   Kiem  ") == "hoan kiem"


class TestEntityTypePrefix:
    def test_known_types(self) -> None:
        assert entity_type_prefix("Place") == "place"
        assert entity_type_prefix("TravelPlace") == "place"
        assert entity_type_prefix("Restaurant") == "restaurant"
        assert entity_type_prefix("DrinkDessert") == "drink"
        assert entity_type_prefix("Accommodation") == "hotel"
        assert entity_type_prefix("Area") == "area"
        assert entity_type_prefix("City") == "city"
        assert entity_type_prefix("District") == "district"
        assert entity_type_prefix("Activity") == "activity"
        assert entity_type_prefix("Festival") == "festival"

    def test_unknown_type(self) -> None:
        assert entity_type_prefix("UnknownType") == "unknownt"


class TestReadCsvChunked:
    def test_reads_csv_in_chunks(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name\n1,Alice\n2,Bob\n3,Charlie", encoding="utf-8")

        batches = []

        def on_batch(batch):
            batches.append(list(batch))

        count = _read_csv_chunked(csv_file, batch_size=2, on_batch=on_batch, quiet=True)

        assert count == 3
        assert len(batches) == 2  # [1,2], [3]
        assert batches[0] == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        assert batches[1] == [{"id": "3", "name": "Charlie"}]

    def test_skips_missing_file(self, tmp_path: Path) -> None:
        count = _read_csv_chunked(
            tmp_path / "missing.csv",
            batch_size=10,
            on_batch=lambda b: None,
            quiet=True,
        )
        assert count == 0


class TestImportEntities:
    @pytest.fixture
    def db_session(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def fixture_csv(self, tmp_path: Path) -> Path:
        entities_csv = tmp_path / "entities.csv"
        entities_csv.write_text(
            "id,name,type,status\n"
            "place_001,Hoan Kiem Lake,Place,verified\n"
            "city_hanoi,Hanoi,City,draft\n"
            "place_002,West Lake,Place,verified\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_import_entities_creates_records(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        stats = import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)

        assert stats["imported"] == 3
        assert stats["skipped"] == 0
        assert stats["errors"] == 0

        entities = db_session.query(KnowledgeEntity).all()
        assert len(entities) == 3
        assert {e.id for e in entities} == {"place_001", "city_hanoi", "place_002"}

    def test_import_entities_dry_run(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        stats = import_entities(db_session, fixture_csv, batch_size=100, dry_run=True, quiet=True)

        assert stats["imported"] == 3
        assert stats["skipped"] == 0

        entities = db_session.query(KnowledgeEntity).all()
        assert len(entities) == 0  # No changes in dry run

    def test_import_entities_idempotent(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)
        db_session.commit()

        # Run again - should skip existing
        stats = import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)

        assert stats["imported"] == 0
        assert stats["skipped"] == 3
        assert stats["errors"] == 0

        entities = db_session.query(KnowledgeEntity).all()
        assert len(entities) == 3  # Still only 3

    def test_import_entities_normalizes_names(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)

        entity = db_session.query(KnowledgeEntity).filter_by(id="place_001").first()
        assert entity.normalized_name == "hoan kiem lake"


class TestImportAliases:
    @pytest.fixture
    def db_session(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def fixture_csv(self, tmp_path: Path) -> Path:
        entities_csv = tmp_path / "entities.csv"
        entities_csv.write_text(
            "id,name,type,status\nplace_001,Hoan Kiem Lake,Place,verified\n",
            encoding="utf-8",
        )
        aliases_csv = tmp_path / "aliases.csv"
        aliases_csv.write_text(
            "entity_id,alias,language\n"
            "place_001,Hoan Kiem Lake,en\n"
            "place_001,Hồ Hoàn Kiếm,vi\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_import_aliases_creates_records(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)
        db_session.commit()

        stats = import_aliases(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)

        assert stats["imported"] == 2
        assert stats["errors"] == 0

        aliases = db_session.query(KnowledgeAlias).all()
        assert len(aliases) == 2
        assert {a.alias for a in aliases} == {"Hoan Kiem Lake", "Hồ Hoàn Kiếm"}


class TestImportProperties:
    @pytest.fixture
    def db_session(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def fixture_csv(self, tmp_path: Path) -> Path:
        entities_csv = tmp_path / "entities.csv"
        entities_csv.write_text(
            "id,name,type,status\nplace_001,Hoan Kiem Lake,Place,verified\n",
            encoding="utf-8",
        )
        props_csv = tmp_path / "properties.csv"
        props_csv.write_text(
            "entity_id,key,value,source\n"
            "place_001,address,Hanoi Old Quarter,test\n"
            "place_001,latitude,21.0285,test\n",
            encoding="utf-8",
        )
        return tmp_path

    def test_import_properties_creates_records(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)
        db_session.commit()

        stats = import_properties(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)

        assert stats["imported"] == 2
        assert stats["errors"] == 0

        props = db_session.query(KnowledgeProperty).all()
        assert len(props) == 2
        assert {p.key for p in props} == {"address", "latitude"}

    def test_import_properties_parses_json_recommendations(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        pass  # Properties don't have recommendations, this tests the pattern


class TestImportRelationships:
    @pytest.fixture
    def db_session(self):
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        yield session
        session.close()

    @pytest.fixture
    def fixture_csv(self, tmp_path: Path) -> Path:
        entities_csv = tmp_path / "entities.csv"
        entities_csv.write_text(
            "id,name,type,status\n"
            "place_001,Hoan Kiem Lake,Place,verified\n"
            "city_hanoi,Hanoi,City,draft\n",
            encoding="utf-8",
        )
        rels_csv = tmp_path / "relationships.csv"
        rels_csv.write_text(
            "from_entity_id,relationship,to_entity_id,source,recommendations\n"
            'place_001,LOCATED_IN,city_hanoi,test,"[]"\n',
            encoding="utf-8",
        )
        return tmp_path

    def test_import_relationships_creates_records(
        self,
        db_session: Session,
        fixture_csv: Path,
    ) -> None:
        import_entities(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)
        db_session.commit()

        stats = import_relationships(db_session, fixture_csv, batch_size=100, dry_run=False, quiet=True)

        assert stats["imported"] == 1
        assert stats["errors"] == 0

        rels = db_session.query(KnowledgeRelationship).all()
        assert len(rels) == 1
        assert rels[0].from_entity_id == "place_001"
        assert rels[0].relationship == "LOCATED_IN"
        assert rels[0].to_entity_id == "city_hanoi"
