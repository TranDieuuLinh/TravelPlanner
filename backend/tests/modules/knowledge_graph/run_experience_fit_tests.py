#!/usr/bin/env python3
"""Standalone test runner for experience fit evaluation tests.

This runs tests directly without pytest to avoid conftest import issues.
"""

from __future__ import annotations

import sys
import os

if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())

from datetime import datetime, timezone
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    BudgetLevel,
    CheckStatus,
    ExperienceFitInput,
    ScopeResolutionRepository,
    kg_evaluate_experience_fit,
)
from app.modules.knowledge_graph.research.experience_fit_tool import (
    EntityNotFoundError,
    _is_verified_source,
    _compute_overall_status,
    HARD_CONSTRAINTS,
)


def setup_db(use_sqlite=True):
    """Create test database."""
    if use_sqlite:
        engine = create_engine("sqlite:///:memory:", echo=False)

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

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
            conn.execute(text("CREATE INDEX ix_knowledge_relationships_to ON knowledge_relationships(to_entity_id)"))

            conn.commit()
    else:
        db_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel"
        )
        from app.db.base import Base
        engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data setup helpers
# ---------------------------------------------------------------------------

def populate_base_graph(session):
    """Populate basic graph for tests."""
    entities = [
        KnowledgeEntity(
            id="area_vietnam", canonical_name="Vietnam",
            normalized_name="vietnam", entity_type="AreaAdm0",
            status="verified", created_at=now(), updated_at=now(),
        ),
        KnowledgeEntity(
            id="area_hanoi", canonical_name="Hà Nội",
            normalized_name="ha noi", entity_type="AreaAdm1",
            status="verified", created_at=now(), updated_at=now(),
        ),
        KnowledgeEntity(
            id="area_hoan_kiem", canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem", entity_type="AreaAdm2",
            status="verified", created_at=now(), updated_at=now(),
        ),
        KnowledgeEntity(
            id="area_sa_pa", canonical_name="Sa Pa",
            normalized_name="sa pa", entity_type="AreaAdm2",
            status="verified", created_at=now(), updated_at=now(),
        ),
        KnowledgeEntity(
            id="place_hoan_kiem_temple", canonical_name="Văn Miếu",
            normalized_name="van mie u", entity_type="TravelPlace",
            status="verified", created_at=now(), updated_at=now(),
        ),
        KnowledgeEntity(
            id="place_restaurant_hoan_kiem", canonical_name="Restaurant A",
            normalized_name="restaurant a", entity_type="Restaurant",
            status="verified", created_at=now(), updated_at=now(),
        ),
        KnowledgeEntity(
            id="place_outside", canonical_name="Sapa Terraced Fields",
            normalized_name="sapa terraced fields", entity_type="TravelPlace",
            status="verified", created_at=now(), updated_at=now(),
        ),
    ]
    for e in entities:
        session.add(e)
    session.flush()

    rels = [
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="PART_OF",
                             to_entity_id="area_vietnam", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hoan_kiem", relationship_type="PART_OF",
                             to_entity_id="area_hanoi", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_sa_pa", relationship_type="PART_OF",
                             to_entity_id="area_hanoi", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_hoan_kiem_temple", relationship_type="LOCATED_IN",
                             to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_restaurant_hoan_kiem", relationship_type="LOCATED_IN",
                             to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_outside", relationship_type="LOCATED_IN",
                             to_entity_id="area_sa_pa", created_at=now(), updated_at=now()),
    ]
    for r in rels:
        session.add(r)
    session.commit()


def populate_full_props(session):
    """Populate graph with entity that has all relevant properties."""
    entities = [
        KnowledgeEntity(id="area_vietnam", canonical_name="Vietnam",
                       normalized_name="vietnam", entity_type="AreaAdm0",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hanoi", canonical_name="Hà Nội",
                       normalized_name="ha noi", entity_type="AreaAdm1",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hoan_kiem", canonical_name="Hoàn Kiếm",
                       normalized_name="hoan kiem", entity_type="AreaAdm2",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_temple", canonical_name="Văn Miếu",
                       normalized_name="van mie u", entity_type="TravelPlace",
                       status="verified", created_at=now(), updated_at=now()),
    ]
    for e in entities:
        session.add(e)
    session.flush()

    rels = [
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="PART_OF",
                             to_entity_id="area_vietnam", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hoan_kiem", relationship_type="PART_OF",
                             to_entity_id="area_hanoi", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_temple", relationship_type="LOCATED_IN",
                             to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
    ]
    for r in rels:
        session.add(r)

    props = [
        KnowledgeProperty(entity_id="place_temple", key="opening_hours",
                         value="07:00-18:00", source="https://wikipedia.org", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="admission_fee_vnd",
                         value="30000", source="https://vietnamtourism.gov.vn", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="typical_duration_minutes",
                         value="120", source="https://wikipedia.org", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="best_time_slots",
                         value="morning,afternoon", source="https://vietnamtourism.gov.vn", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="booking_required",
                         value="false", source="https://vietnamtourism.gov.vn", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="accessibility_features",
                         value="wheelchair,hearing_loop", source="https://official.gov.vn", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="suitable_for",
                         value="solo,group,family", source="https://vietnamtourism.gov.vn", updated_at=now()),
        KnowledgeProperty(entity_id="place_temple", key="weather_constraints",
                         value="avoid monsoon season", source="https://vietnamtourism.gov.vn", updated_at=now()),
    ]
    for p in props:
        session.add(p)
    session.commit()


def populate_booking_required_no_url(session):
    """Entity that requires booking but has no URL."""
    entities = [
        KnowledgeEntity(id="area_vietnam", canonical_name="Vietnam",
                       normalized_name="vietnam", entity_type="AreaAdm0",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hanoi", canonical_name="Hà Nội",
                       normalized_name="ha noi", entity_type="AreaAdm1",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hoan_kiem", canonical_name="Hoàn Kiếm",
                       normalized_name="hoan kiem", entity_type="AreaAdm2",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_museum", canonical_name="National Museum",
                       normalized_name="national museum", entity_type="TravelPlace",
                       status="verified", created_at=now(), updated_at=now()),
    ]
    for e in entities:
        session.add(e)
    session.flush()

    rels = [
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="PART_OF",
                             to_entity_id="area_vietnam", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hoan_kiem", relationship_type="PART_OF",
                             to_entity_id="area_hanoi", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_museum", relationship_type="LOCATED_IN",
                             to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
    ]
    for r in rels:
        session.add(r)

    props = [
        KnowledgeProperty(entity_id="place_museum", key="booking_required",
                         value="true", source="https://official.gov.vn", updated_at=now()),
    ]
    for p in props:
        session.add(p)
    session.commit()


def populate_booking_required_with_url(session):
    """Entity that requires booking AND has a booking URL."""
    entities = [
        KnowledgeEntity(id="area_vietnam", canonical_name="Vietnam",
                       normalized_name="vietnam", entity_type="AreaAdm0",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hanoi", canonical_name="Hà Nội",
                       normalized_name="ha noi", entity_type="AreaAdm1",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hoan_kiem", canonical_name="Hoàn Kiếm",
                       normalized_name="hoan kiem", entity_type="AreaAdm2",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_theater", canonical_name="Water Puppet Theater",
                       normalized_name="water puppet theater", entity_type="TravelPlace",
                       status="verified", created_at=now(), updated_at=now()),
    ]
    for e in entities:
        session.add(e)
    session.flush()

    rels = [
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="PART_OF",
                             to_entity_id="area_vietnam", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hoan_kiem", relationship_type="PART_OF",
                             to_entity_id="area_hanoi", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_theater", relationship_type="LOCATED_IN",
                             to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
    ]
    for r in rels:
        session.add(r)

    props = [
        KnowledgeProperty(entity_id="place_theater", key="booking_required",
                         value="true", source="https://booking.com", updated_at=now()),
        KnowledgeProperty(entity_id="place_theater", key="booking_url",
                         value="https://ticket.vn/theater", source="https://booking.com", updated_at=now()),
    ]
    for p in props:
        session.add(p)
    session.commit()


def populate_unverified_source(session):
    """Entity with unverified (AI-inferred) opening hours."""
    entities = [
        KnowledgeEntity(id="area_vietnam", canonical_name="Vietnam",
                       normalized_name="vietnam", entity_type="AreaAdm0",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hanoi", canonical_name="Hà Nội",
                       normalized_name="ha noi", entity_type="AreaAdm1",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hoan_kiem", canonical_name="Hoàn Kiếm",
                       normalized_name="hoan kiem", entity_type="AreaAdm2",
                       status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_mystery", canonical_name="Mystery Place",
                       normalized_name="mystery place", entity_type="TravelPlace",
                       status="verified", created_at=now(), updated_at=now()),
    ]
    for e in entities:
        session.add(e)
    session.flush()

    rels = [
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="PART_OF",
                             to_entity_id="area_vietnam", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hoan_kiem", relationship_type="PART_OF",
                             to_entity_id="area_hanoi", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_mystery", relationship_type="LOCATED_IN",
                             to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
    ]
    for r in rels:
        session.add(r)

    props = [
        KnowledgeProperty(entity_id="place_mystery", key="opening_hours",
                         value="09:00-17:00", source=None, updated_at=now()),
    ]
    for p in props:
        session.add(p)
    session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

PASSED = 0
FAILED = 0


def run(test_fn, *args):
    global PASSED, FAILED
    try:
        test_fn(*args)
        PASSED += 1
        print(f"  PASS: {test_fn.__name__}")
    except AssertionError as e:
        FAILED += 1
        print(f"  FAIL: {test_fn.__name__}: {e}")


# --- Provenance tests ---

def test_verified_official():
    assert _is_verified_source("https://official.gov.vn") is True


def test_verified_wikipedia():
    assert _is_verified_source("https://wikipedia.org") is True


def test_verified_booking():
    assert _is_verified_source("https://booking.com") is True


def test_verified_agoda():
    assert _is_verified_source("https://agoda.com") is True


def test_unverified_none():
    assert _is_verified_source(None) is False


def test_unverified_ai():
    assert _is_verified_source("ai-inferred") is False


def test_unverified_random():
    assert _is_verified_source("some random source") is False


# --- Overall status tests ---

def test_all_supported():
    from app.modules.knowledge_graph.research.schema import DimensionCheck
    checks = [
        DimensionCheck(dimension="opening_hours", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="admission_fee", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
    ]
    assert _compute_overall_status(checks) == CheckStatus.SUPPORTED


def test_hard_conflict_wins():
    from app.modules.knowledge_graph.research.schema import DimensionCheck
    checks = [
        DimensionCheck(dimension="geographic_scope", status=CheckStatus.CONFLICTED,
                       reason="outside", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="opening_hours", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="admission_fee", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
    ]
    assert _compute_overall_status(checks) == CheckStatus.CONFLICTED


def test_excluded_type_conflict_wins():
    from app.modules.knowledge_graph.research.schema import DimensionCheck
    checks = [
        DimensionCheck(dimension="excluded_type", status=CheckStatus.CONFLICTED,
                       reason="excluded", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="opening_hours", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
    ]
    assert _compute_overall_status(checks) == CheckStatus.CONFLICTED


def test_no_conflict_critical_unknown():
    from app.modules.knowledge_graph.research.schema import DimensionCheck
    checks = [
        DimensionCheck(dimension="geographic_scope", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="opening_hours", status=CheckStatus.UNKNOWN,
                       reason="no data", evidenceClaimIds=[], sources=[]),
    ]
    assert _compute_overall_status(checks) == CheckStatus.UNKNOWN


def test_non_critical_unknown_supported():
    from app.modules.knowledge_graph.research.schema import DimensionCheck
    checks = [
        DimensionCheck(dimension="geographic_scope", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="excluded_type", status=CheckStatus.SUPPORTED,
                       reason="ok", evidenceClaimIds=[], sources=[]),
        DimensionCheck(dimension="weather_constraints", status=CheckStatus.UNKNOWN,
                       reason="no data", evidenceClaimIds=[], sources=[]),
    ]
    assert _compute_overall_status(checks) == CheckStatus.SUPPORTED


# --- Input validation tests ---

def test_requires_entity_or_claim(repo):
    try:
        input_data = ExperienceFitInput(
            destination="Hà Nội", days=3, partySize=2,
        )
        kg_evaluate_experience_fit(repo, input_data)
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "entityId or claimId" in str(e)


def test_cannot_provide_both(repo):
    try:
        input_data = ExperienceFitInput(
            entityId="place_temple", claimId="claim_123",
            destination="Hà Nội", days=3, partySize=2,
        )
        kg_evaluate_experience_fit(repo, input_data)
        raise AssertionError("Expected ValueError")
    except ValueError as e:
        assert "not both" in str(e)


def test_entity_not_found_error(repo):
    try:
        input_data = ExperienceFitInput(
            entityId="nonexistent_entity",
            destination="Hà Nội", days=3, partySize=2,
        )
        kg_evaluate_experience_fit(repo, input_data)
        raise AssertionError("Expected EntityNotFoundError")
    except EntityNotFoundError as e:
        assert "nonexistent_entity" in str(e)
        assert "not found" in str(e)


# --- Excluded type tests ---

def test_excluded_type_conflicted(repo):
    input_data = ExperienceFitInput(
        entityId="place_restaurant_hoan_kiem",
        destination="Hoàn Kiếm", days=3, partySize=2,
        excludedPlaceTypes=["Restaurant"],
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "excluded_type")
    assert check.status == CheckStatus.CONFLICTED
    assert "Restaurant" in check.reason


def test_type_not_excluded_supported(repo):
    input_data = ExperienceFitInput(
        entityId="place_hoan_kiem_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
        excludedPlaceTypes=["Restaurant"],
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "excluded_type")
    assert check.status == CheckStatus.SUPPORTED


def test_no_exclusions_supported(repo):
    input_data = ExperienceFitInput(
        entityId="place_restaurant_hoan_kiem",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "excluded_type")
    assert check.status == CheckStatus.SUPPORTED


# --- Geographic scope tests ---

def test_entity_in_scope_supported(repo):
    input_data = ExperienceFitInput(
        entityId="place_hoan_kiem_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "geographic_scope")
    assert check.status == CheckStatus.SUPPORTED


def test_entity_outside_scope_conflicted(repo):
    input_data = ExperienceFitInput(
        entityId="place_outside",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "geographic_scope")
    assert check.status == CheckStatus.CONFLICTED


def test_unknown_destination_unknown(repo):
    input_data = ExperienceFitInput(
        entityId="place_hoan_kiem_temple",
        destination="UnknownLand", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "geographic_scope")
    assert check.status == CheckStatus.UNKNOWN


# --- Opening hours tests ---

def test_verified_opening_hours_supported(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    check = next(c for c in result.checks if c.dimension == "opening_hours")
    assert check.status == CheckStatus.SUPPORTED


def test_missing_opening_hours_unknown(repo):
    input_data = ExperienceFitInput(
        entityId="place_hoan_kiem_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    check = next(c for c in result.checks if c.dimension == "opening_hours")
    assert check.status == CheckStatus.UNKNOWN


def test_unverified_source_unknown(repo_unverified):
    input_data = ExperienceFitInput(
        entityId="place_mystery",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_unverified, input_data)
    check = next(c for c in result.checks if c.dimension == "opening_hours")
    assert check.status == CheckStatus.UNKNOWN
    assert "not verified" in check.reason.lower() or "inferred" in check.reason.lower()


# --- Booking required tests ---

def test_booking_required_with_url_supported(repo_booking_url):
    input_data = ExperienceFitInput(
        entityId="place_theater",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_booking_url, input_data)
    check = next(c for c in result.checks if c.dimension == "booking_required")
    assert check.status == CheckStatus.SUPPORTED
    assert "booking URL" in check.reason


def test_booking_required_without_url_conflicted(repo_booking_no_url):
    input_data = ExperienceFitInput(
        entityId="place_museum",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_booking_no_url, input_data)
    check = next(c for c in result.checks if c.dimension == "booking_required")
    assert check.status == CheckStatus.CONFLICTED
    # Overall should be conflicted because booking_required is a hard constraint
    assert result.overallStatus == CheckStatus.CONFLICTED


# --- Admission fee tests ---

def test_fee_within_budget_supported(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
        budgetTargetAmount=100000,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    check = next(c for c in result.checks if c.dimension == "admission_fee")
    assert check.status == CheckStatus.SUPPORTED


def test_fee_exceeds_budget_conflicted(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
        budgetTargetAmount=10000,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    check = next(c for c in result.checks if c.dimension == "admission_fee")
    assert check.status == CheckStatus.CONFLICTED


# --- Accessibility tests ---

def test_all_features_available_supported(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
        accessibilityRequirements=["wheelchair"],
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    check = next(c for c in result.checks if c.dimension == "accessibility")
    assert check.status == CheckStatus.SUPPORTED


def test_missing_features_conflicted(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
        accessibilityRequirements=["wheelchair", "guide_dog"],
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    check = next(c for c in result.checks if c.dimension == "accessibility")
    assert check.status == CheckStatus.CONFLICTED
    assert "guide_dog" in check.reason


def test_no_requirements_supported(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    check = next(c for c in result.checks if c.dimension == "accessibility")
    assert check.status == CheckStatus.SUPPORTED


# --- Overall result tests ---

def test_hard_conflict_overrides_supported(repo):
    input_data = ExperienceFitInput(
        entityId="place_outside",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    assert result.overallStatus == CheckStatus.CONFLICTED


# --- Deterministic output tests ---

def test_checks_are_sorted(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result1 = kg_evaluate_experience_fit(repo_full, input_data)
    result2 = kg_evaluate_experience_fit(repo_full, input_data)
    dims1 = [c.dimension for c in result1.checks]
    dims2 = [c.dimension for c in result2.checks]
    assert dims1 == dims2
    assert dims1 == sorted(dims1)


def test_same_input_same_output(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
        accessibilityRequirements=["wheelchair"],
    )
    result1 = kg_evaluate_experience_fit(repo_full, input_data)
    result2 = kg_evaluate_experience_fit(repo_full, input_data)
    assert result1.overallStatus == result2.overallStatus
    assert len(result1.checks) == len(result2.checks)
    for c1, c2 in zip(result1.checks, result2.checks):
        assert c1.dimension == c2.dimension
        assert c1.status == c2.status
        assert c1.reason == c2.reason


# --- Output schema tests ---

def test_output_has_required_fields(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    assert result.entity is not None
    assert result.entity.id == "place_temple"
    assert result.entity.name == "Văn Miếu"
    assert result.entity.type == "TravelPlace"
    assert result.overallStatus in list(CheckStatus)
    assert isinstance(result.checks, list)
    assert isinstance(result.warnings, list)


def test_each_check_has_required_fields(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    for check in result.checks:
        assert check.dimension
        assert check.status in list(CheckStatus)
        assert check.reason
        assert isinstance(check.evidenceClaimIds, list)
        assert isinstance(check.sources, list)


def test_all_dimensions_present(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    expected = {
        "geographic_scope", "excluded_type", "opening_hours",
        "typical_duration", "time_slot", "booking_required",
        "admission_fee", "accessibility", "suitable_for",
        "requirements", "weather_constraints", "provenance_trust",
    }
    actual = {c.dimension for c in result.checks}
    assert actual == expected


def test_claim_id_works(repo):
    input_data = ExperienceFitInput(
        claimId="place_hoan_kiem_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo, input_data)
    assert result.entity is not None
    assert result.entity.id == "place_hoan_kiem_temple"


def test_output_json_serialization(repo_full):
    input_data = ExperienceFitInput(
        entityId="place_temple",
        destination="Hoàn Kiếm", days=3, partySize=2,
    )
    result = kg_evaluate_experience_fit(repo_full, input_data)
    json_str = result.model_dump_json(by_alias=True)
    assert "overallStatus" in json_str
    assert "checks" in json_str
    assert "entity" in json_str


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global PASSED, FAILED

    print("\n" + "=" * 60)
    print("EXPERIENCE FIT TOOL - STANDALONE TESTS")
    print("=" * 60 + "\n")

    # --- Provenance tests ---
    print("=== Provenance (source verification) ===")
    for fn in [test_verified_official, test_verified_wikipedia, test_verified_booking,
               test_verified_agoda, test_unverified_none, test_unverified_ai,
               test_unverified_random]:
        run(fn)

    # --- Overall status computation tests ---
    print("\n=== Overall Status Computation ===")
    for fn in [test_all_supported, test_hard_conflict_wins, test_excluded_type_conflict_wins,
               test_no_conflict_critical_unknown, test_non_critical_unknown_supported]:
        run(fn)

    # --- Input validation tests ---
    print("\n=== Input Validation ===")
    db_empty = setup_db(use_sqlite=True)
    repo_empty = ScopeResolutionRepository(db_empty)
    for fn in [test_requires_entity_or_claim, test_cannot_provide_both,
               test_entity_not_found_error]:
        run(fn, repo_empty)
    db_empty.close()

    # --- Excluded type tests ---
    print("\n=== Excluded Type Dimension ===")
    db_base = setup_db(use_sqlite=True)
    populate_base_graph(db_base)
    repo_base = ScopeResolutionRepository(db_base)
    for fn in [test_excluded_type_conflicted, test_type_not_excluded_supported,
               test_no_exclusions_supported]:
        run(fn, repo_base)

    # --- Geographic scope tests ---
    print("\n=== Geographic Scope Dimension ===")
    for fn in [test_entity_in_scope_supported, test_entity_outside_scope_conflicted,
               test_unknown_destination_unknown]:
        run(fn, repo_base)

    # --- Opening hours tests ---
    print("\n=== Opening Hours Dimension ===")
    db_full = setup_db(use_sqlite=True)
    populate_full_props(db_full)
    repo_full = ScopeResolutionRepository(db_full)

    db_unverified = setup_db(use_sqlite=True)
    populate_unverified_source(db_unverified)
    repo_unverified = ScopeResolutionRepository(db_unverified)

    for fn in [test_verified_opening_hours_supported, test_missing_opening_hours_unknown,
               test_unverified_source_unknown]:
        if fn.__name__ == "test_unverified_source_unknown":
            run(fn, repo_unverified)
        elif fn.__name__ == "test_missing_opening_hours_unknown":
            run(fn, repo_base)
        else:
            run(fn, repo_full)

    # --- Booking required tests ---
    print("\n=== Booking Required Dimension ===")
    db_booking_url = setup_db(use_sqlite=True)
    populate_booking_required_with_url(db_booking_url)
    repo_booking_url = ScopeResolutionRepository(db_booking_url)

    db_booking_no_url = setup_db(use_sqlite=True)
    populate_booking_required_no_url(db_booking_no_url)
    repo_booking_no_url = ScopeResolutionRepository(db_booking_no_url)

    for fn in [test_booking_required_with_url_supported, test_booking_required_without_url_conflicted]:
        if fn.__name__ == "test_booking_required_without_url_conflicted":
            run(fn, repo_booking_no_url)
        else:
            run(fn, repo_booking_url)

    # --- Admission fee tests ---
    print("\n=== Admission Fee Dimension ===")
    for fn in [test_fee_within_budget_supported, test_fee_exceeds_budget_conflicted]:
        run(fn, repo_full)

    # --- Accessibility tests ---
    print("\n=== Accessibility Dimension ===")
    for fn in [test_all_features_available_supported, test_missing_features_conflicted,
               test_no_requirements_supported]:
        run(fn, repo_full)

    # --- Overall result tests ---
    print("\n=== Overall Result ===")
    run(test_hard_conflict_overrides_supported, repo_base)

    # --- Deterministic output tests ---
    print("\n=== Deterministic Output ===")
    for fn in [test_checks_are_sorted, test_same_input_same_output]:
        run(fn, repo_full)

    # --- Output schema tests ---
    print("\n=== Output Schema ===")
    for fn in [test_output_has_required_fields, test_each_check_has_required_fields,
               test_all_dimensions_present, test_claim_id_works,
               test_output_json_serialization]:
        if fn.__name__ == "test_claim_id_works":
            run(fn, repo_base)
        else:
            run(fn, repo_full)

    # Cleanup
    db_base.close()
    db_full.close()
    db_unverified.close()
    db_booking_url.close()
    db_booking_no_url.close()

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60 + "\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
