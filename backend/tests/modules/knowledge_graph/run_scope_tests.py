#!/usr/bin/env python3
"""Standalone test runner for scope resolution tests.

This runs tests directly without pytest to avoid conftest import issues.
"""

from __future__ import annotations

import sys
import os

# Ensure backend directory is in path
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    ScopeResolveInput,
    ScopeResolutionRepository,
    kg_resolve_scope,
)


def setup_db(use_sqlite=True):
    """Create test database.
    
    Args:
        use_sqlite: If True, use SQLite (with proper schema for testing)
                   If False, use PostgreSQL (requires running DB)
    """
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import sessionmaker
    
    if use_sqlite:
        engine = create_engine("sqlite:///:memory:", echo=False)
        
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        
        # Create tables manually matching the SQLAlchemy models
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE knowledge_entities (
                    id TEXT PRIMARY KEY,
                    canonical_name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
            """))
            
            conn.execute(text("CREATE INDEX ix_knowledge_entities_normalized ON knowledge_entities(normalized_name)"))
            conn.execute(text("CREATE INDEX ix_knowledge_entities_type ON knowledge_entities(entity_type)"))
            
            conn.execute(text("""
                CREATE TABLE knowledge_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    normalized_alias TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'en',
                    created_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("CREATE INDEX ix_knowledge_aliases_entity ON knowledge_aliases(entity_id)"))
            conn.execute(text("CREATE INDEX ix_knowledge_aliases_normalized ON knowledge_aliases(normalized_alias)"))
            
            conn.execute(text("""
                CREATE TABLE knowledge_properties (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES knowledge_entities(id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("CREATE INDEX ix_knowledge_properties_entity ON knowledge_properties(entity_id)"))
            
            conn.execute(text("""
                CREATE TABLE knowledge_relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_entity_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    to_entity_id TEXT NOT NULL,
                    recommendations TEXT,
                    source TEXT,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (from_entity_id) REFERENCES knowledge_entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (to_entity_id) REFERENCES knowledge_entities(id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("CREATE INDEX ix_knowledge_relationships_from ON knowledge_relationships(from_entity_id)"))
            conn.execute(text("CREATE INDEX ix_knowledge_relationships_type ON knowledge_relationships(relationship_type)"))
            
            conn.commit()
    else:
        import os
        db_url = os.environ.get(
            "DATABASE_URL", 
            "postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel"
        )
        engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def populate_db(session):
    """Populate test database."""
    from datetime import datetime, timezone
    
    entities = [
        KnowledgeEntity(
            id="area_vietnam",
            canonical_name="Vietnam",
            normalized_name="vietnam",
            entity_type="AreaAdm0",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeEntity(
            id="area_ba_dinh",
            canonical_name="Ba Đình",
            normalized_name="ba dinh",
            entity_type="AreaAdm2",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeEntity(
            id="area_legacy",
            canonical_name="Old Area",
            normalized_name="old area",
            entity_type="Area",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeEntity(
            id="place_starbucks_hoan_kiem",
            canonical_name="Starbucks Hoàn Kiếm",
            normalized_name="starbucks hoan kiem",
            entity_type="Restaurant",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeEntity(
            id="place_temple_of_literature",
            canonical_name="Văn Miếu",
            normalized_name="van mie u",
            entity_type="TravelPlace",
            status="verified",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]
    for entity in entities:
        session.add(entity)
    session.flush()  # Ensure entities are committed before adding aliases

    aliases = [
        KnowledgeAlias(
            entity_id="area_hanoi",
            alias="Hanoi",
            normalized_alias="hanoi",
            language="en",
            created_at=datetime.now(timezone.utc),
        ),
        KnowledgeAlias(
            entity_id="area_hoan_kiem",
            alias="Hoan Kiem",
            normalized_alias="hoan kiem",
            language="en",
            created_at=datetime.now(timezone.utc),
        ),
        KnowledgeAlias(
            entity_id="area_hoan_kiem",
            alias="Quận Hoàn Kiếm",
            normalized_alias="quan hoan kiem",
            language="vi",
            created_at=datetime.now(timezone.utc),
        ),
    ]
    for alias in aliases:
        session.add(alias)
    session.flush()

    relationships = [
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_vietnam",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeRelationship(
            from_entity_id="area_hoan_kiem",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeRelationship(
            from_entity_id="area_ba_dinh",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeRelationship(
            from_entity_id="place_starbucks_hoan_kiem",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        KnowledgeRelationship(
            from_entity_id="place_temple_of_literature",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    ]
    for rel in relationships:
        session.add(rel)

    session.commit()


def test_stats_empty(repo):
    """Test stats return zeros for empty graph."""
    stats = repo.stats()
    assert stats.entityCount == 0, f"Expected 0, got {stats.entityCount}"
    assert stats.aliasCount == 0
    assert stats.relationshipCount == 0
    assert stats.areaCount == 0
    assert stats.areaAdm0Count == 0
    assert stats.areaAdm1Count == 0
    assert stats.areaAdm2Count == 0
    print("  PASS: test_stats_empty")


def test_stats_with_data(repo):
    """Test stats return correct counts."""
    stats = repo.stats()
    assert stats.entityCount == 7
    assert stats.aliasCount == 3
    assert stats.relationshipCount == 5
    assert stats.areaAdm0Count == 1
    assert stats.areaAdm1Count == 1
    assert stats.areaAdm2Count == 2
    assert stats.areaCount == 1
    print("  PASS: test_stats_with_data")


def test_is_empty_true(repo):
    """Test is_empty returns True for empty graph."""
    assert repo.is_empty() is True
    print("  PASS: test_is_empty_true")


def test_is_empty_false(repo):
    """Test is_empty returns False for populated graph."""
    assert repo.is_empty() is False
    print("  PASS: test_is_empty_false")


def test_resolve_canonical_name(repo):
    """Test resolving area by canonical name."""
    result = repo.resolve_area_by_name("Hà Nội")
    assert result is not None
    assert result.id == "area_hanoi"
    assert result.entity_type == "AreaAdm1"
    print("  PASS: test_resolve_canonical_name")


def test_resolve_alias(repo):
    """Test resolving area by alias."""
    result = repo.resolve_area_by_name("Hanoi")
    assert result is not None
    assert result.id == "area_hanoi"
    print("  PASS: test_resolve_alias")


def test_resolve_vietnamese_alias(repo):
    """Test resolving area by Vietnamese alias with diacritics."""
    result = repo.resolve_area_by_name("Quận Hoàn Kiếm")
    assert result is not None
    assert result.id == "area_hoan_kiem"
    print("  PASS: test_resolve_vietnamese_alias")


def test_resolve_case_insensitive(repo):
    """Test resolving area is case insensitive."""
    result = repo.resolve_area_by_name("hà nội")
    assert result is not None
    assert result.id == "area_hanoi"
    print("  PASS: test_resolve_case_insensitive")


def test_resolve_not_found(repo):
    """Test resolving non-existent area returns None."""
    result = repo.resolve_area_by_name("NonExistentPlace")
    assert result is None
    print("  PASS: test_resolve_not_found")


def test_resolve_non_area_entity_returns_none(repo):
    """Test resolving a Place entity returns None (only Area types allowed)."""
    result = repo.resolve_area_by_name("Starbucks Hoàn Kiếm")
    assert result is None
    print("  PASS: test_resolve_non_area_entity_returns_none")


def test_traverse_ancestors(repo):
    """Test traversing PART_OF ancestors."""
    ancestors = repo.traverse_part_of_ancestors("area_hoan_kiem", max_depth=4)
    assert len(ancestors) == 2, f"Expected 2 ancestors, got {len(ancestors)}"
    assert ancestors[0].id == "area_hanoi"
    assert ancestors[0].depth == 1
    assert ancestors[1].id == "area_vietnam"
    assert ancestors[1].depth == 2
    print("  PASS: test_traverse_ancestors")


def test_traverse_ancestors_max_depth(repo):
    """Test ancestor traversal respects max_depth."""
    ancestors = repo.traverse_part_of_ancestors("area_hoan_kiem", max_depth=1)
    assert len(ancestors) == 1
    assert ancestors[0].id == "area_hanoi"
    print("  PASS: test_traverse_ancestors_max_depth")


def test_traverse_descendants(repo):
    """Test traversing PART_OF descendants."""
    descendants = repo.traverse_part_of_descendants("area_hanoi", max_depth=4)
    assert len(descendants) == 2
    descendant_ids = {d.id for d in descendants}
    assert "area_hoan_kiem" in descendant_ids
    assert "area_ba_dinh" in descendant_ids
    print("  PASS: test_traverse_descendants")


def test_traverse_descendants_with_limit(repo):
    """Test descendant traversal respects limit."""
    descendants = repo.traverse_part_of_descendants(
        "area_hanoi", max_depth=4, limit=1
    )
    assert len(descendants) == 1
    print("  PASS: test_traverse_descendants_with_limit")


def test_traverse_no_descendants(repo):
    """Test traversal of leaf node returns empty list."""
    descendants = repo.traverse_part_of_descendants("area_hoan_kiem", max_depth=4)
    assert len(descendants) == 0
    print("  PASS: test_traverse_no_descendants")


def test_map_single_place_to_area(repo):
    """Test mapping a single place to its area."""
    areas = repo.map_places_to_areas(["place_starbucks_hoan_kiem"])
    assert len(areas) == 1
    assert areas[0].id == "area_hoan_kiem"
    print("  PASS: test_map_single_place_to_area")


def test_map_multiple_places_same_area(repo):
    """Test mapping multiple places in same area returns unique areas."""
    areas = repo.map_places_to_areas([
        "place_starbucks_hoan_kiem",
        "place_temple_of_literature",
    ])
    assert len(areas) == 1
    assert areas[0].id == "area_hoan_kiem"
    print("  PASS: test_map_multiple_places_same_area")


def test_map_empty_place_list(repo):
    """Test mapping empty place list returns empty result."""
    areas = repo.map_places_to_areas([])
    assert len(areas) == 0
    print("  PASS: test_map_empty_place_list")


def test_map_place_without_location(repo):
    """Test mapping place without LOCATED_IN relationship returns empty."""
    areas = repo.map_places_to_areas(["area_hanoi"])
    assert len(areas) == 0
    print("  PASS: test_map_place_without_location")


def test_resolve_scope_by_canonical_name(repo):
    """Test resolving scope by canonical name."""
    input_data = ScopeResolveInput(destination="Hà Nội")
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is not None
    assert result.rootArea.id == "area_hanoi"
    assert result.rootArea.name == "Hà Nội"
    assert result.rootArea.type == "AreaAdm1"
    assert len(result.ancestors) == 1
    assert result.ancestors[0].id == "area_vietnam"
    print("  PASS: test_resolve_scope_by_canonical_name")


def test_resolve_scope_by_alias(repo):
    """Test resolving scope by alias."""
    input_data = ScopeResolveInput(destination="Hanoi")
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is not None
    assert result.rootArea.id == "area_hanoi"
    print("  PASS: test_resolve_scope_by_alias")


def test_resolve_scope_normalize_vietnamese(repo):
    """Test resolving scope normalizes Vietnamese diacritics."""
    input_data = ScopeResolveInput(destination="hoan kiem")
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is not None
    assert result.rootArea.id == "area_hoan_kiem"
    print("  PASS: test_resolve_scope_normalize_vietnamese")


def test_resolve_scope_not_found(repo):
    """Test resolving non-existent area returns None root."""
    input_data = ScopeResolveInput(destination="NonExistent")
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is None
    assert result.ancestors == []
    assert result.includedAreas == []
    print("  PASS: test_resolve_scope_not_found")


def test_resolve_scope_includes_descendants(repo):
    """Test scope includes descendant areas."""
    input_data = ScopeResolveInput(destination="Hà Nội")
    result = kg_resolve_scope(repo, input_data)

    assert len(result.includedAreas) == 2
    descendant_ids = {a.id for a in result.includedAreas}
    assert "area_hoan_kiem" in descendant_ids
    assert "area_ba_dinh" in descendant_ids
    print("  PASS: test_resolve_scope_includes_descendants")


def test_resolve_scope_selected_places(repo):
    """Test scope includes areas from selected places."""
    input_data = ScopeResolveInput(
        destination="Vietnam",
        selectedPlaceIds=["place_starbucks_hoan_kiem"],
    )
    result = kg_resolve_scope(repo, input_data)

    assert len(result.selectedPlaceAreas) == 1
    assert result.selectedPlaceAreas[0].id == "area_hoan_kiem"
    print("  PASS: test_resolve_scope_selected_places")


def test_resolve_scope_respects_max_depth(repo):
    """Test scope resolution respects maxDepth parameter."""
    input_data = ScopeResolveInput(destination="Hà Nội", maxDepth=1)
    result = kg_resolve_scope(repo, input_data)

    # With maxDepth=1, ancestor traversal should include 1 ancestor (Vietnam is depth 1)
    # But descendants are limited by resultLimit
    assert len(result.ancestors) == 1, f"Expected 1 ancestor, got {len(result.ancestors)}: {[a.id for a in result.ancestors]}"
    assert len(result.includedAreas) == 2
    print("  PASS: test_resolve_scope_respects_max_depth")


def test_resolve_scope_respects_result_limit(repo):
    """Test scope resolution respects resultLimit parameter."""
    input_data = ScopeResolveInput(destination="Hà Nội", resultLimit=1)
    result = kg_resolve_scope(repo, input_data)

    assert len(result.includedAreas) == 1
    print("  PASS: test_resolve_scope_respects_result_limit")


def test_resolve_scope_legacy_area_warning(repo):
    """Test resolving legacy Area type produces warning."""
    input_data = ScopeResolveInput(destination="Old Area")
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is not None
    assert any("LEGACY_AREA_TYPE" in w for w in result.warnings)
    print("  PASS: test_resolve_scope_legacy_area_warning")


def test_resolve_scope_empty_graph_warning(repo):
    """Test resolving scope on empty graph produces warning."""
    input_data = ScopeResolveInput(destination="Hà Nội")
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is None
    assert any("KNOWLEDGE_GRAPH_EMPTY" in w for w in result.warnings)
    print("  PASS: test_resolve_scope_empty_graph_warning")


def test_resolve_scope_deterministic_ordering(repo):
    """Test scope results are deterministically ordered."""
    input_data = ScopeResolveInput(destination="Hà Nội")
    result1 = kg_resolve_scope(repo, input_data)
    result2 = kg_resolve_scope(repo, input_data)

    assert [a.id for a in result1.includedAreas] == [a.id for a in result2.includedAreas]
    assert [a.id for a in result1.ancestors] == [a.id for a in result2.ancestors]
    print("  PASS: test_resolve_scope_deterministic_ordering")


def test_resolve_scope_full_hierarchy(repo):
    """Test resolving scope from leaf area includes full hierarchy."""
    input_data = ScopeResolveInput(destination="Hoàn Kiếm", maxDepth=4)
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is not None
    assert result.rootArea.id == "area_hoan_kiem"
    assert len(result.ancestors) == 2
    assert result.ancestors[0].id == "area_hanoi"
    assert result.ancestors[1].id == "area_vietnam"
    assert result.includedAreas == []
    print("  PASS: test_resolve_scope_full_hierarchy")


def test_resolve_scope_with_all_parameters(repo):
    """Test resolving scope with all parameters set."""
    input_data = ScopeResolveInput(
        destination="Vietnam",
        selectedPlaceIds=["place_starbucks_hoan_kiem", "place_temple_of_literature"],
        maxDepth=4,
        resultLimit=50,
    )
    result = kg_resolve_scope(repo, input_data)

    assert result.rootArea is not None
    assert result.rootArea.type == "AreaAdm0"
    assert len(result.ancestors) == 0
    # Vietnam has 1 direct child (Hanoi), which has 2 children
    assert len(result.includedAreas) == 3, f"Expected 3 descendants, got {len(result.includedAreas)}: {[a.id for a in result.includedAreas]}"
    assert len(result.selectedPlaceAreas) == 1
    print("  PASS: test_resolve_scope_with_all_parameters")


def run_tests():
    """Run all tests."""
    # Always use SQLite for tests to avoid affecting production database
    print("\nUsing database: SQLite (in-memory) for tests")
    
    # Test empty graph (using SQLite)
    print("\n=== Running Empty DB Tests ===")
    db_empty = setup_db(use_sqlite=True)
    repo_empty = ScopeResolutionRepository(db_empty)
    
    test_stats_empty(repo_empty)
    test_is_empty_true(repo_empty)
    
    # Empty graph warning test
    print("  Running: test_resolve_scope_empty_graph_warning")
    input_data = ScopeResolveInput(destination="Hà Nội")
    result = kg_resolve_scope(repo_empty, input_data)
    assert result.rootArea is None
    assert any("KNOWLEDGE_GRAPH_EMPTY" in w for w in result.warnings)
    print("  PASS: test_resolve_scope_empty_graph_warning")
    
    db_empty.close()
    
    # Populated tests (using SQLite)
    print("\n=== Running Populated DB Tests ===")
    db = setup_db(use_sqlite=True)
    try:
        populate_db(db)
        repo = ScopeResolutionRepository(db)
        print("  Database setup complete")
    except Exception as e:
        print(f"  ERROR during setup: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return
    
    # Stats tests
    print("  Running: test_stats_with_data")
    try:
        test_stats_with_data(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_is_empty_false")
    test_is_empty_false(repo)
    
    # Area resolution tests
    print("  Running: test_resolve_canonical_name")
    test_resolve_canonical_name(repo)
    
    print("  Running: test_resolve_alias")
    test_resolve_alias(repo)
    
    print("  Running: test_resolve_vietnamese_alias")
    test_resolve_vietnamese_alias(repo)
    
    print("  Running: test_resolve_case_insensitive")
    test_resolve_case_insensitive(repo)
    
    print("  Running: test_resolve_not_found")
    test_resolve_not_found(repo)
    
    print("  Running: test_resolve_non_area_entity_returns_none")
    test_resolve_non_area_entity_returns_none(repo)
    
    # Hierarchy traversal tests
    print("  Running: test_traverse_ancestors")
    test_traverse_ancestors(repo)
    
    print("  Running: test_traverse_ancestors_max_depth")
    test_traverse_ancestors_max_depth(repo)
    
    print("  Running: test_traverse_descendants")
    test_traverse_descendants(repo)
    
    print("  Running: test_traverse_descendants_with_limit")
    test_traverse_descendants_with_limit(repo)
    
    print("  Running: test_traverse_no_descendants")
    test_traverse_no_descendants(repo)
    
    # Place mapping tests
    print("  Running: test_map_single_place_to_area")
    test_map_single_place_to_area(repo)
    
    print("  Running: test_map_multiple_places_same_area")
    test_map_multiple_places_same_area(repo)
    
    print("  Running: test_map_empty_place_list")
    test_map_empty_place_list(repo)
    
    print("  Running: test_map_place_without_location")
    test_map_place_without_location(repo)
    
    # Scope resolution tests
    print("  Running: test_resolve_scope_by_canonical_name")
    try:
        test_resolve_scope_by_canonical_name(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_by_alias")
    try:
        test_resolve_scope_by_alias(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_normalize_vietnamese")
    try:
        test_resolve_scope_normalize_vietnamese(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_not_found")
    try:
        test_resolve_scope_not_found(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_includes_descendants")
    try:
        test_resolve_scope_includes_descendants(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_selected_places")
    try:
        test_resolve_scope_selected_places(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_respects_max_depth")
    try:
        test_resolve_scope_respects_max_depth(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_respects_result_limit")
    try:
        test_resolve_scope_respects_result_limit(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_legacy_area_warning")
    try:
        test_resolve_scope_legacy_area_warning(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_deterministic_ordering")
    try:
        test_resolve_scope_deterministic_ordering(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    # Integration tests
    print("  Running: test_resolve_scope_full_hierarchy")
    try:
        test_resolve_scope_full_hierarchy(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    print("  Running: test_resolve_scope_with_all_parameters")
    try:
        test_resolve_scope_with_all_parameters(repo)
        print("    PASS")
    except AssertionError as e:
        print(f"    FAILED: {e}")
        db.close()
        return
    
    db.close()
    
    print("\n" + "=" * 50)
    print("ALL TESTS PASSED!")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    try:
        run_tests()
        sys.exit(0)
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
