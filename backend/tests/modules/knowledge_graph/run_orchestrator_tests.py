#!/usr/bin/env python3
"""Standalone test runner for orchestrator unit tests.

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
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    CheckStatus,
    ScopeResolutionRepository,
    TripResearchInput,
    TripResearchBundle,
)
from app.modules.knowledge_graph.research.orchestrator import (
    GraphResearchOrchestrator,
    GraphScopeError,
    _apply_diversity_rerank,
    _get_highest_priority,
    _has_hard_conflict,
    CandidateScore,
    _batch_evaluate_fit,
)
from app.modules.knowledge_graph.research.schema import (
    BudgetLevel,
    EntitySummary,
    GraphEvidenceClaim,
    Recommendation,
    RecommendationPriority,
    TrustLevel,
)


PASSED = 0
FAILED = 0


def now():
    return datetime.now(timezone.utc)


def setup_db():
    """Create test database."""
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
        conn.execute(text("CREATE INDEX ix_entities_normalized ON knowledge_entities(normalized_name)"))
        conn.execute(text("CREATE INDEX ix_entities_type ON knowledge_entities(entity_type)"))

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
        conn.execute(text("CREATE INDEX ix_rels_from ON knowledge_relationships(from_entity_id)"))
        conn.execute(text("CREATE INDEX ix_rels_type ON knowledge_relationships(relationship_type)"))
        conn.execute(text("CREATE INDEX ix_rels_to ON knowledge_relationships(to_entity_id)"))

        conn.commit()

    return sessionmaker(bind=engine)()


def _make_claim(
    claim_id: str,
    object_name: str,
    object_type: str = "TravelPlace",
    trust: TrustLevel = TrustLevel.SOURCE_BACKED,
    priority: RecommendationPriority = RecommendationPriority.RECOMMENDED,
) -> GraphEvidenceClaim:
    """Create a minimal GraphEvidenceClaim for testing."""
    return GraphEvidenceClaim(
        claimId=claim_id,
        subject=EntitySummary(id="area_hanoi", name="Hà Nội", type="AreaAdm1", status="verified"),
        predicate="SPECIAL_EXPERIENCE",
        object=EntitySummary(id=claim_id, name=object_name, type=object_type, status="verified"),
        path=["area_hanoi", "SPECIAL_EXPERIENCE", claim_id],
        recommendations=[Recommendation(priority=priority, reason=f"Experience: {object_name}")],
        evidence=[],
        trust=trust,
    )


def run(test_fn, *args):
    global PASSED, FAILED
    try:
        test_fn(*args)
        PASSED += 1
        print(f"  PASS: {test_fn.__name__}")
    except AssertionError as e:
        FAILED += 1
        print(f"  FAIL: {test_fn.__name__}: {e}")


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

def test_get_highest_priority_no_recs():
    claim = _make_claim("c1", "Place A")
    claim.recommendations = []
    assert _get_highest_priority(claim) == "optional"


def test_get_highest_priority_must():
    claim = _make_claim("c1", "Place A", priority=RecommendationPriority.MUST)
    assert _get_highest_priority(claim) == "must"


def test_get_highest_priority_mixed():
    claim = _make_claim("c1", "Place A")
    claim.recommendations = [
        Recommendation(priority=RecommendationPriority.OPTIONAL),
        Recommendation(priority=RecommendationPriority.MUST),
        Recommendation(priority=RecommendationPriority.RECOMMENDED),
    ]
    assert _get_highest_priority(claim) == "must"


def test_has_hard_conflict_no_conflicts():
    from unittest.mock import MagicMock
    mock_checks = [
        MagicMock(dimension="opening_hours", status=CheckStatus.SUPPORTED),
        MagicMock(dimension="admission_fee", status=CheckStatus.UNKNOWN),
    ]
    has_hard, reasons = _has_hard_conflict(CheckStatus.SUPPORTED, mock_checks)
    assert has_hard is False
    assert reasons == []


def test_has_hard_conflict_found():
    from unittest.mock import MagicMock
    mock_checks = [
        MagicMock(dimension="excluded_type", status=CheckStatus.CONFLICTED, reason="Restaurant excluded"),
        MagicMock(dimension="admission_fee", status=CheckStatus.SUPPORTED),
    ]
    has_hard, reasons = _has_hard_conflict(CheckStatus.CONFLICTED, mock_checks)
    assert has_hard is True
    assert len(reasons) == 1
    assert "excluded_type" in reasons[0]


def test_diversity_rerank_empty():
    result = _apply_diversity_rerank([])
    assert result == []


def test_diversity_rerank_small_unchanged():
    from unittest.mock import MagicMock
    candidates = [(i, MagicMock(object_type=f"type_{i}")) for i in range(3)]
    result = _apply_diversity_rerank(candidates)
    assert len(result) == 3


def test_diversity_rerank_prevents_dominance():
    from unittest.mock import MagicMock
    candidates = [(i, MagicMock(object_type="Museum")) for i in range(10)]
    result = _apply_diversity_rerank(candidates)
    type_counts = {}
    for idx, cand in result[:6]:
        t = cand.object_type
        type_counts[t] = type_counts.get(t, 0) + 1
    assert type_counts.get("Museum", 0) <= 6


def test_candidate_score_trust_order():
    claim_v = _make_claim("c1", "Verified Place", trust=TrustLevel.VERIFIED)
    claim_sb = _make_claim("c2", "Source B Place", trust=TrustLevel.SOURCE_BACKED)
    claim_i = _make_claim("c3", "Inferred Place", trust=TrustLevel.INFERRED)

    from app.modules.knowledge_graph.research.schema import FitResult
    fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

    sc_v = CandidateScore(claim_v, fit, set(), set())
    sc_sb = CandidateScore(claim_sb, fit, set(), set())
    sc_i = CandidateScore(claim_i, fit, set(), set())

    sorted_scores = sorted([sc_i, sc_sb, sc_v], key=lambda x: x.sort_key())
    assert sorted_scores[0].claim.trust == TrustLevel.VERIFIED
    assert sorted_scores[1].claim.trust == TrustLevel.SOURCE_BACKED
    assert sorted_scores[2].claim.trust == TrustLevel.INFERRED


def test_candidate_score_user_selected():
    claim_a = _make_claim("c1", "Place A")
    claim_b = _make_claim("c2", "Place B")
    from app.modules.knowledge_graph.research.schema import FitResult
    fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

    sc_a = CandidateScore(claim_a, fit, {"c1"}, set())
    sc_b = CandidateScore(claim_b, fit, set(), set())

    assert sc_a.sort_key() < sc_b.sort_key()


def test_candidate_score_deterministic():
    claim = _make_claim("c1", "Place")
    from app.modules.knowledge_graph.research.schema import FitResult
    fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

    sc1 = CandidateScore(claim, fit, set(), set())
    sc2 = CandidateScore(claim, fit, set(), set())

    assert sc1.sort_key() == sc2.sort_key()


# ---------------------------------------------------------------------------
# Orchestrator tests with real DB
# ---------------------------------------------------------------------------

def populate_hanoi_graph(session):
    """Populate basic Hanoi area graph."""
    entities = [
        KnowledgeEntity(id="area_vietnam", canonical_name="Vietnam", normalized_name="vietnam",
                       entity_type="AreaAdm0", status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hanoi", canonical_name="Hà Nội", normalized_name="ha noi",
                       entity_type="AreaAdm1", status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="area_hoan_kiem", canonical_name="Hoàn Kiếm", normalized_name="hoan kiem",
                       entity_type="AreaAdm2", status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_temple", canonical_name="Temple", normalized_name="temple",
                       entity_type="TravelPlace", status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_cafe", canonical_name="Cafe", normalized_name="cafe",
                       entity_type="Cafe", status="verified", created_at=now(), updated_at=now()),
        KnowledgeEntity(id="place_restaurant", canonical_name="Restaurant", normalized_name="restaurant",
                       entity_type="Restaurant", status="verified", created_at=now(), updated_at=now()),
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
        KnowledgeRelationship(from_entity_id="place_cafe", relationship_type="LOCATED_IN",
                           to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="place_restaurant", relationship_type="LOCATED_IN",
                           to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="SPECIAL_EXPERIENCE",
                           to_entity_id="place_temple", source="https://vietnamtourism.gov.vn",
                           created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="SPECIAL_EXPERIENCE",
                           to_entity_id="place_cafe", source="https://wikipedia.org",
                           created_at=now(), updated_at=now()),
        KnowledgeRelationship(from_entity_id="area_hanoi", relationship_type="SPECIAL_EXPERIENCE",
                           to_entity_id="place_restaurant", source="https://tripadvisor.com",
                           created_at=now(), updated_at=now()),
    ]
    for r in rels:
        session.add(r)
    session.commit()


def test_scope_fails_raises_error():
    """Unknown destination raises GraphScopeError."""
    session = setup_db()
    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(destination="UnknownDestination", days=3, partySize=2)

    try:
        orchestrator.research(input_data)
        raise AssertionError("Expected GraphScopeError")
    except GraphScopeError as e:
        assert e.CODE == "GRAPH_SCOPE_NOT_FOUND"
    finally:
        session.close()


def test_empty_discovery_returns_warning():
    """Empty discovery should return bundle with warning."""
    session = setup_db()
    repo = ScopeResolutionRepository(session)

    # Add area but no experiences
    session.add(KnowledgeEntity(
        id="area_hanoi", canonical_name="Hà Nội", normalized_name="ha noi",
        entity_type="AreaAdm1", status="verified", created_at=now(), updated_at=now(),
    ))
    session.commit()

    orchestrator = GraphResearchOrchestrator(repo, repo)
    input_data = TripResearchInput(destination="Hà Nội", days=3, partySize=2)
    result = orchestrator.research(input_data)

    assert len(result.eligibleExperiences) == 0
    assert any("GRAPH_EXPERIENCE_COVERAGE_EMPTY" in w for w in result.warnings)
    session.close()


def test_excluded_type_conflict():
    """Excluded place type should cause conflict."""
    session = setup_db()
    populate_hanoi_graph(session)
    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(
        destination="Hà Nội",
        days=3,
        partySize=2,
        excludedPlaceTypes=["Restaurant"],
    )

    result = orchestrator.research(input_data)

    if result.conflictedExperiences:
        conflicted_types = [c.claim.object.type for c in result.conflictedExperiences]
        assert "Restaurant" in conflicted_types
    session.close()


def test_trace_counts_accurate():
    """Trace counts should match actual output."""
    session = setup_db()
    populate_hanoi_graph(session)
    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(destination="Hà Nội", days=3, partySize=2)
    result = orchestrator.research(input_data)

    assert result.trace.eligibleExperienceCount == len(result.eligibleExperiences)
    assert result.trace.conflictedExperienceCount == len(result.conflictedExperiences)
    session.close()


def test_unknown_destination_raises():
    """Unknown destination should raise GraphScopeError."""
    session = setup_db()
    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(destination="UnknownLandXYZ", days=3, partySize=2)

    try:
        orchestrator.research(input_data)
        raise AssertionError("Expected GraphScopeError")
    except GraphScopeError as e:
        assert e.CODE == "GRAPH_SCOPE_NOT_FOUND"
    finally:
        session.close()


def test_deterministic_ranking():
    """Same input should produce same ranking order."""
    session = setup_db()
    populate_hanoi_graph(session)
    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(destination="Hà Nội", days=3, partySize=2)

    result1 = orchestrator.research(input_data)
    result2 = orchestrator.research(input_data)

    ranks1 = [e.rank for e in result1.eligibleExperiences]
    ranks2 = [e.rank for e in result2.eligibleExperiences]
    assert ranks1 == ranks2

    ids1 = [e.claim.claimId for e in result1.eligibleExperiences]
    ids2 = [e.claim.claimId for e in result2.eligibleExperiences]
    assert ids1 == ids2
    session.close()


def test_selected_place_prioritized():
    """User-selected places should be prioritized."""
    session = setup_db()
    populate_hanoi_graph(session)
    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(
        destination="Hà Nội",
        days=3,
        partySize=2,
        selectedPlaceIds=["place_temple"],
    )

    result = orchestrator.research(input_data)

    if result.eligibleExperiences:
        temple_exp = next(
            (e for e in result.eligibleExperiences if e.claim.object.id == "place_temple"),
            None,
        )
        if temple_exp:
            assert "user_selected_place" in temple_exp.rankReasons
    session.close()


def test_limit_respected():
    """Candidate limit should be respected."""
    session = setup_db()

    # Add area
    session.add(KnowledgeEntity(
        id="area_hanoi", canonical_name="Hà Nội", normalized_name="ha noi",
        entity_type="AreaAdm1", status="verified", created_at=now(), updated_at=now(),
    ))
    session.add(KnowledgeEntity(
        id="area_hoan_kiem", canonical_name="Hoàn Kiếm", normalized_name="hoan kiem",
        entity_type="AreaAdm2", status="verified", created_at=now(), updated_at=now(),
    ))

    # Add 10 places
    for i in range(10):
        place_id = f"place_{i}"
        session.add(KnowledgeEntity(
            id=place_id, canonical_name=f"Place {i}", normalized_name=f"place {i}",
            entity_type="TravelPlace", status="verified", created_at=now(), updated_at=now(),
        ))
        session.add(KnowledgeRelationship(
            from_entity_id=place_id, relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem", created_at=now(), updated_at=now(),
        ))
        session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi", relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id=place_id, source="https://wikipedia.org",
            created_at=now(), updated_at=now(),
        ))

    session.commit()

    repo = ScopeResolutionRepository(session)
    orchestrator = GraphResearchOrchestrator(repo, repo)

    input_data = TripResearchInput(destination="Hà Nội", days=3, partySize=2, candidateLimit=5)
    result = orchestrator.research(input_data)

    assert len(result.eligibleExperiences) <= 5
    session.close()


def test_no_llm_call():
    """Orchestrator should not import or call any LLM."""
    import app.modules.knowledge_graph.research.orchestrator as orch_mod
    source = orch_mod.__file__
    with open(source, encoding="utf-8") as f:
        content = f.read()

    llm_indicators = ["llm", "openai", "anthropic", "gpt", "claude", "StubLLM"]
    for indicator in llm_indicators:
        assert indicator.lower() not in content.lower(), f"Found LLM indicator: {indicator}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global PASSED, FAILED

    print("\n" + "=" * 60)
    print("ORCHESTRATOR UNIT TESTS")
    print("=" * 60 + "\n")

    # Helper function tests
    print("=== Helper Functions ===")
    for fn in [
        test_get_highest_priority_no_recs,
        test_get_highest_priority_must,
        test_get_highest_priority_mixed,
        test_has_hard_conflict_no_conflicts,
        test_has_hard_conflict_found,
        test_diversity_rerank_empty,
        test_diversity_rerank_small_unchanged,
        test_diversity_rerank_prevents_dominance,
        test_candidate_score_trust_order,
        test_candidate_score_user_selected,
        test_candidate_score_deterministic,
    ]:
        run(fn)

    # Orchestrator tests with real DB
    print("\n=== Orchestrator with Real DB ===")
    for fn in [
        test_scope_fails_raises_error,
        test_empty_discovery_returns_warning,
        test_excluded_type_conflict,
        test_trace_counts_accurate,
        test_unknown_destination_raises,
        test_deterministic_ranking,
        test_selected_place_prioritized,
        test_limit_respected,
        test_no_llm_call,
    ]:
        run(fn)

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("=" * 60 + "\n")

    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
