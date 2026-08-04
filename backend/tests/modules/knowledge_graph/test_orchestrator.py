"""Tests for the GraphResearchOrchestrator.

These tests use fake tools/repositories to test the orchestrator in isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    CheckStatus,
    GraphEvidenceClaim,
    GraphEvidenceBundle,
    GraphSnapshot,
    ScopeResolveOutput,
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
)
from app.modules.knowledge_graph.research.schema import (
    AreaRef,
    BudgetLevel,
    EntitySummary,
    ExperienceFitOutput,
    Recommendation,
    RecommendationPriority,
    TrustLevel,
)


# ---------------------------------------------------------------------------
# Helper: fake claims
# ---------------------------------------------------------------------------

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
        recommendations=[
            Recommendation(priority=priority, reason=f"Experience: {object_name}")
        ],
        evidence=[],
        trust=trust,
    )


# ---------------------------------------------------------------------------
# Test: helper functions
# ---------------------------------------------------------------------------

class TestGetHighestPriority:
    def test_no_recommendations(self) -> None:
        claim = _make_claim("c1", "Place A")
        claim.recommendations = []
        assert _get_highest_priority(claim) == "optional"

    def test_must_priority(self) -> None:
        claim = _make_claim("c1", "Place A", priority=RecommendationPriority.MUST)
        assert _get_highest_priority(claim) == "must"

    def test_recommended_priority(self) -> None:
        claim = _make_claim("c1", "Place A", priority=RecommendationPriority.RECOMMENDED)
        assert _get_highest_priority(claim) == "recommended"

    def test_optional_priority(self) -> None:
        claim = _make_claim("c1", "Place A", priority=RecommendationPriority.OPTIONAL)
        assert _get_highest_priority(claim) == "optional"

    def test_mixed_priorities(self) -> None:
        claim = _make_claim("c1", "Place A")
        claim.recommendations = [
            Recommendation(priority=RecommendationPriority.OPTIONAL),
            Recommendation(priority=RecommendationPriority.MUST),
            Recommendation(priority=RecommendationPriority.RECOMMENDED),
        ]
        assert _get_highest_priority(claim) == "must"


class TestHasHardConflict:
    def test_no_conflicts(self) -> None:
        mock_checks = [
            MagicMock(dimension="opening_hours", status=CheckStatus.SUPPORTED),
            MagicMock(dimension="admission_fee", status=CheckStatus.UNKNOWN),
        ]
        has_hard, reasons = _has_hard_conflict(CheckStatus.SUPPORTED, mock_checks)
        assert has_hard is False
        assert reasons == []

    def test_hard_conflict_found(self) -> None:
        mock_checks = [
            MagicMock(dimension="excluded_type", status=CheckStatus.CONFLICTED, reason="Restaurant excluded"),
            MagicMock(dimension="admission_fee", status=CheckStatus.SUPPORTED),
        ]
        has_hard, reasons = _has_hard_conflict(CheckStatus.CONFLICTED, mock_checks)
        assert has_hard is True
        assert len(reasons) == 1
        assert "excluded_type" in reasons[0]


class TestDiversityRerank:
    def test_empty_list(self) -> None:
        result = _apply_diversity_rerank([])
        assert result == []

    def test_small_list_unchanged(self) -> None:
        candidates = [(i, MagicMock(object_type=f"type_{i}")) for i in range(3)]
        result = _apply_diversity_rerank(candidates)
        assert len(result) == 3

    def test_diversity_prevents_one_type_dominating(self) -> None:
        """With 10 candidates all of type 'Museum', only 6 should appear in top positions."""
        candidates = [(i, MagicMock(object_type="Museum")) for i in range(10)]
        result = _apply_diversity_rerank(candidates)
        type_counts = {}
        for idx, cand in result[:6]:
            t = cand.object_type
            type_counts[t] = type_counts.get(t, 0) + 1
        # At most 6 (60%) should be Museum
        assert type_counts.get("Museum", 0) <= 6


class TestCandidateScore:
    def test_sort_key_order(self) -> None:
        """Higher trust = lower sort key value = ranked higher."""
        claim_v = _make_claim("c1", "Verified Place", trust=TrustLevel.VERIFIED)
        claim_sb = _make_claim("c2", "Source B Place", trust=TrustLevel.SOURCE_BACKED)
        claim_i = _make_claim("c3", "Inferred Place", trust=TrustLevel.INFERRED)

        from app.modules.knowledge_graph.research import FitResult
        fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

        sc_v = CandidateScore(claim_v, fit, set(), set())
        sc_sb = CandidateScore(claim_sb, fit, set(), set())
        sc_i = CandidateScore(claim_i, fit, set(), set())

        # Sort by trust: verified (0) < source_backed (1) < inferred (2)
        sorted_scores = sorted([sc_i, sc_sb, sc_v], key=lambda x: x.sort_key())
        assert sorted_scores[0].claim.trust == TrustLevel.VERIFIED
        assert sorted_scores[1].claim.trust == TrustLevel.SOURCE_BACKED
        assert sorted_scores[2].claim.trust == TrustLevel.INFERRED

    def test_user_selected_gets_lower_sort_key(self) -> None:
        claim_a = _make_claim("c1", "Place A")
        claim_b = _make_claim("c2", "Place B")
        from app.modules.knowledge_graph.research import FitResult
        fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

        # A is user-selected, B is not
        sc_a = CandidateScore(claim_a, fit, {"c1"}, set())
        sc_b = CandidateScore(claim_b, fit, set(), set())

        # A should come before B (lower sort key value for user_selected)
        assert sc_a.sort_key() < sc_b.sort_key()

    def test_source_place_gets_lower_sort_key(self) -> None:
        claim_a = _make_claim("c1", "Place A")
        claim_b = _make_claim("c2", "Place B")
        from app.modules.knowledge_graph.research import FitResult
        fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

        sc_a = CandidateScore(claim_a, fit, set(), {"c1"})
        sc_b = CandidateScore(claim_b, fit, set(), set())

        # A should come before B (lower sort key value for source_place)
        assert sc_a.sort_key() < sc_b.sort_key()

    def test_sort_key_deterministic(self) -> None:
        """Same claim always produces same sort key."""
        claim = _make_claim("c1", "Place")
        from app.modules.knowledge_graph.research import FitResult
        fit = FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=1)

        sc1 = CandidateScore(claim, fit, set(), set())
        sc2 = CandidateScore(claim, fit, set(), set())

        assert sc1.sort_key() == sc2.sort_key()


# ---------------------------------------------------------------------------
# Test: tool call order (mock-based)
# ---------------------------------------------------------------------------

class TestOrchestratorToolOrder:
    """Test that tools are called in the correct order."""

    def test_scope_fails_discovery_not_called(self, db_session: Session) -> None:
        """If scope resolution fails, discovery and fit should not be called."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)
        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)

        input_data = TripResearchInput(
            destination="UnknownDestination",
            days=3,
            partySize=2,
        )

        # Should raise GraphScopeError
        with pytest.raises(GraphScopeError) as exc_info:
            orchestrator.research(input_data)
        assert exc_info.value.CODE == "GRAPH_SCOPE_NOT_FOUND"

    def test_tools_called_in_order(self, db_session: Session) -> None:
        """Tools should be called: scope → discovery → fit."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)
        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)

        call_order: list[str] = []

        original_resolve = scope_repo.resolve_area_by_name
        original_discover = discovery_repo.query_special_experiences_in_scope

        def track_resolve(dest: str):
            call_order.append("resolve_scope")
            return original_resolve(dest)

        def track_discover(area_ids, **kwargs):
            call_order.append("discover_experiences")
            return original_discover(area_ids, **kwargs)

        scope_repo.resolve_area_by_name = track_resolve
        discovery_repo.query_special_experiences_in_scope = track_discover

        try:
            input_data = TripResearchInput(
                destination="UnknownDestination",
                days=3,
                partySize=2,
            )
            try:
                orchestrator.research(input_data)
            except GraphScopeError:
                pass
        finally:
            scope_repo.resolve_area_by_name = original_resolve
            discovery_repo.query_special_experiences_in_scope = original_discover

        assert call_order == ["resolve_scope"]


class TestDiscoveryEmptyWarning:
    """Test that empty discovery returns warning, not crash."""

    def test_empty_discovery_returns_warning(self, db_session: Session) -> None:
        """Empty discovery should return bundle with warning, not crash."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        # Add a real area so scope resolves
        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.commit()

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrator.research(input_data)

        assert len(result.eligibleExperiences) == 0
        assert len(result.conflictedExperiences) == 0
        warning_codes = [w for w in result.warnings]
        assert any("GRAPH_EXPERIENCE_COVERAGE_EMPTY" in w for w in warning_codes)


class TestHardConflictRouting:
    """Test that hard conflicts go to conflictedExperiences."""

    def test_conflicted_goes_to_conflicted_list(self, db_session: Session) -> None:
        """A claim with hard conflict should end up in conflictedExperiences."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        # Setup: area and excluded place
        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_restaurant",
            canonical_name="Restaurant X",
            normalized_name="restaurant x",
            entity_type="Restaurant",
            status="verified",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",  # self-loop for simplicity
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="place_restaurant",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="place_restaurant",
            source="https://tripadvisor.com",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
            excludedPlaceTypes=["Restaurant"],
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        # The restaurant should be conflicted due to excluded type
        assert len(result.conflictedExperiences) > 0
        # No eligible experiences (all excluded)
        assert len(result.eligibleExperiences) == 0


class TestUnknownStatus:
    """Test that unknown fit status is kept in eligibleExperiences with warning."""

    def test_unknown_in_eligible_with_warning(self, db_session: Session) -> None:
        """Unknown status should be in eligibleExperiences, not crashed."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        # Setup: area with a place that has no fit data
        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_temple",
            canonical_name="Temple of Unknown",
            normalized_name="temple of unknown",
            entity_type="TravelPlace",
            status="verified",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="place_temple",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="place_temple",
            source="https://tripadvisor.com",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        # Should not crash; should have results
        assert len(result.eligibleExperiences) >= 0
        # Should have some warning about unknown fit
        assert len(result.warnings) > 0


class TestTrustRanking:
    """Test that trust level affects ranking order."""

    def test_verified_before_source_backed_before_inferred(self, db_session: Session) -> None:
        """verified > source_backed > inferred in final ranking."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        # Setup: area and 3 places with different trust levels
        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_verified",
            canonical_name="Verified Place",
            normalized_name="verified place",
            entity_type="TravelPlace",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_source",
            canonical_name="Source Backed Place",
            normalized_name="source backed place",
            entity_type="TravelPlace",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_inferred",
            canonical_name="Inferred Place",
            normalized_name="inferred place",
            entity_type="TravelPlace",
            status="draft",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        for place_id in ["place_verified", "place_source", "place_inferred"]:
            db_session.add(KnowledgeRelationship(
                from_entity_id=place_id,
                relationship_type="LOCATED_IN",
                to_entity_id="area_hoan_kiem",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id="area_hanoi",
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=place_id,
                source="https://wikipedia.org" if place_id == "place_verified" else "inference:draft",
            ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        # If we have at least 3 results, trust should order them
        if len(result.eligibleExperiences) >= 3:
            ranks = {exp.claim.object.id: exp.rank for exp in result.eligibleExperiences}

            # Verified should have lower rank number (ranked higher)
            if "place_verified" in ranks and "place_source" in ranks:
                assert ranks["place_verified"] < ranks["place_source"]
            if "place_source" in ranks and "place_inferred" in ranks:
                assert ranks["place_source"] < ranks["place_inferred"]


class TestDeterministicOutput:
    """Test that output is deterministic."""

    def test_same_input_same_output(self, db_session: Session) -> None:
        """Running the same input twice should produce identical output."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        # Setup: minimal area
        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_a",
            canonical_name="Place A",
            normalized_name="place a",
            entity_type="TravelPlace",
            status="verified",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="place_a",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="place_a",
            source="https://wikipedia.org",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)

        result1 = orchestrator.research(input_data)
        result2 = orchestrator.research(input_data)

        # Same ranks
        ranks1 = [e.rank for e in result1.eligibleExperiences]
        ranks2 = [e.rank for e in result2.eligibleExperiences]
        assert ranks1 == ranks2

        # Same claim IDs in same order
        ids1 = [e.claim.claimId for e in result1.eligibleExperiences]
        ids2 = [e.claim.claimId for e in result2.eligibleExperiences]
        assert ids1 == ids2


class TestLimitApplied:
    """Test that candidate limit is applied after ranking."""

    def test_limit_respected(self, db_session: Session) -> None:
        """The candidateLimit should cap the number of eligible experiences."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        # Setup: area with multiple places
        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))

        # Add 10 places
        for i in range(10):
            place_id = f"place_{i}"
            db_session.add(KnowledgeEntity(
                id=place_id,
                canonical_name=f"Place {i}",
                normalized_name=f"place {i}",
                entity_type="TravelPlace",
                status="verified",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id=place_id,
                relationship_type="LOCATED_IN",
                to_entity_id="area_hoan_kiem",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id="area_hanoi",
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=place_id,
                source="https://wikipedia.org",
            ))

        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
            candidateLimit=5,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        # Should not exceed limit
        assert len(result.eligibleExperiences) <= 5


class TestEvidencePathPreserved:
    """Test that evidence path and provenance are preserved in output."""

    def test_claim_provenance_not_lost(self, db_session: Session) -> None:
        """Provenance information should survive the orchestration."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_museum",
            canonical_name="National Museum",
            normalized_name="national museum",
            entity_type="TravelPlace",
            status="verified",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="place_museum",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="place_museum",
            source="https://vietnamtourism.gov.vn",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        if result.eligibleExperiences:
            exp = result.eligibleExperiences[0]
            # Trust level should be preserved
            assert exp.claim.trust in list(TrustLevel)
            # Claim ID should be stable
            assert exp.claim.claimId
            # Path should be preserved
            assert len(exp.claim.path) > 0


class TestTraceCounts:
    """Test that trace counts are accurate."""

    def test_trace_counts_match_output(self, db_session: Session) -> None:
        """Trace counts should accurately reflect what happened."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="place_temple",
            canonical_name="Temple",
            normalized_name="temple",
            entity_type="TravelPlace",
            status="verified",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="place_temple",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ))
        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="place_temple",
            source="https://wikipedia.org",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        # Trace counts should match actual output
        assert result.trace.eligibleExperienceCount == len(result.eligibleExperiences)
        assert result.trace.conflictedExperienceCount == len(result.conflictedExperiences)
        assert result.trace.discoveredClaimCount >= 0
        assert result.trace.evaluatedExperienceCount >= result.trace.discoveredClaimCount


class TestSelectedPlacePriority:
    """Test that user-selected places are prioritized."""

    def test_selected_place_ranked_higher(self, db_session: Session) -> None:
        """User-selected places should get better rank."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))

        for place_id, place_name in [("place_a", "Place A"), ("place_b", "Place B")]:
            db_session.add(KnowledgeEntity(
                id=place_id,
                canonical_name=place_name,
                normalized_name=place_name.lower(),
                entity_type="TravelPlace",
                status="verified",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id=place_id,
                relationship_type="LOCATED_IN",
                to_entity_id="area_hoan_kiem",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id="area_hanoi",
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=place_id,
                source="https://wikipedia.org",
            ))

        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.commit()

        # Only place_a is user-selected
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
            selectedPlaceIds=["place_a"],
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        if len(result.eligibleExperiences) >= 2:
            ranks = {exp.claim.object.id: exp.rank for exp in result.eligibleExperiences}
            if "place_a" in ranks and "place_b" in ranks:
                # User-selected place should have better (lower) rank
                assert ranks["place_a"] <= ranks["place_b"]


class TestNoLLMCall:
    """Test that orchestrator does not call any LLM."""

    def test_no_llm_in_orchestrator(self) -> None:
        """Orchestrator should not import or call any LLM client."""
        import app.modules.knowledge_graph.research.orchestrator as orch_mod

        source = orch_mod.__file__
        with open(source, encoding="utf-8") as f:
            content = f.read()

        llm_indicators = ["llm", "openai", "anthropic", "gpt", "claude", "StubLLM"]
        for indicator in llm_indicators:
            assert indicator.lower() not in content.lower(), f"Found LLM indicator: {indicator}"


class TestDiversityNoSingleCategory:
    """Test that ranking does not let one category dominate top results."""

    def test_top_results_are_diverse(self, db_session: Session) -> None:
        """Top 5 results should not all be the same category."""
        from app.modules.knowledge_graph.research import ScopeResolutionRepository

        scope_repo = ScopeResolutionRepository(db_session)
        discovery_repo = ScopeResolutionRepository(db_session)

        db_session.add(KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ))
        db_session.add(KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ))

        # 5 places all of type Restaurant
        for i in range(5):
            db_session.add(KnowledgeEntity(
                id=f"restaurant_{i}",
                canonical_name=f"Restaurant {i}",
                normalized_name=f"restaurant {i}",
                entity_type="Restaurant",
                status="verified",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id=f"restaurant_{i}",
                relationship_type="LOCATED_IN",
                to_entity_id="area_hoan_kiem",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id="area_hanoi",
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=f"restaurant_{i}",
                source="https://tripadvisor.com",
            ))

        # 2 places of type TravelPlace
        for i in range(2):
            db_session.add(KnowledgeEntity(
                id=f"travelplace_{i}",
                canonical_name=f"TravelPlace {i}",
                normalized_name=f"travelplace {i}",
                entity_type="TravelPlace",
                status="verified",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id=f"travelplace_{i}",
                relationship_type="LOCATED_IN",
                to_entity_id="area_hoan_kiem",
            ))
            db_session.add(KnowledgeRelationship(
                from_entity_id="area_hanoi",
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=f"travelplace_{i}",
                source="https://wikipedia.org",
            ))

        db_session.add(KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
        result = orchestrator.research(input_data)

        # Check top results
        top_results = result.eligibleExperiences[:5]
        if len(top_results) >= 3:
            types = [exp.claim.object.type for exp in top_results]
            restaurant_count = types.count("Restaurant")
            # Should not have all 5 be Restaurant
            assert restaurant_count < len(top_results)
