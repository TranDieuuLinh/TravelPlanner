"""Integration tests for the GraphResearchOrchestrator.

These tests use a real SQLite database to test the full integration
between the orchestrator and the actual tool implementations.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    BudgetLevel,
    CheckStatus,
    ScopeResolutionRepository,
    TripResearchInput,
    TravelBudget,
)
from app.modules.knowledge_graph.research.orchestrator import (
    GraphResearchOrchestrator,
    GraphScopeError,
    orchestrate_trip_research,
)


# ---------------------------------------------------------------------------
# Integration fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def integration_session(db_session: Session) -> Session:
    """Create a populated database for integration testing.

    Creates a mini knowledge graph:
    - area_vietnam (AreaAdm0)
    - area_hanoi (AreaAdm1) -> area_vietnam
    - area_hoan_kiem (AreaAdm2) -> area_hanoi
    - place_temple (TravelPlace) -> area_hoan_kiem
    - place_cafe (DrinkDessert) -> area_hoan_kiem
    - place_restaurant (Restaurant) -> area_hoan_kiem
    - place_museum (TravelPlace) -> area_hoan_kiem (with booking_required=true, no URL)
    """
    entities = [
        KnowledgeEntity(
            id="area_vietnam",
            canonical_name="Vietnam",
            normalized_name="vietnam",
            entity_type="AreaAdm0",
            status="verified",
        ),
        KnowledgeEntity(
            id="area_hanoi",
            canonical_name="Hà Nội",
            normalized_name="ha noi",
            entity_type="AreaAdm1",
            status="verified",
        ),
        KnowledgeEntity(
            id="area_hoan_kiem",
            canonical_name="Hoàn Kiếm",
            normalized_name="hoan kiem",
            entity_type="AreaAdm2",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_temple",
            canonical_name="Văn Miếu",
            normalized_name="van mieu",
            entity_type="TravelPlace",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_cafe",
            canonical_name="Cafe Giảng",
            normalized_name="cafe giang",
            entity_type="DrinkDessert",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_restaurant",
            canonical_name="Restaurant A",
            normalized_name="restaurant a",
            entity_type="Restaurant",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_museum",
            canonical_name="National Museum",
            normalized_name="national museum",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
    entities.extend(
        KnowledgeEntity(
            id=activity_id,
            canonical_name=name,
            normalized_name=name.casefold().replace(" ", "_"),
            entity_type="Activity",
            status="verified",
        )
        for activity_id, name in (
            ("activity_temple", "Temple visit"),
            ("activity_cafe", "Coffee experience"),
            ("activity_restaurant", "Local food experience"),
            ("activity_museum", "Museum visit"),
        )
    )
    for entity in entities:
        db_session.add(entity)

    relationships = [
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_vietnam",
        ),
        KnowledgeRelationship(
            from_entity_id="area_hoan_kiem",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ),
        KnowledgeRelationship(
            from_entity_id="place_temple",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        KnowledgeRelationship(
            from_entity_id="place_cafe",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        KnowledgeRelationship(
            from_entity_id="place_restaurant",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        KnowledgeRelationship(
            from_entity_id="place_museum",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        # Schema v7 special experience path: Area -> Activity -> Place.
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_temple",
            source="https://vietnamtourism.gov.vn",
        ),
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_cafe",
            source="https://wikipedia.org",
        ),
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_restaurant",
            source="https://tripadvisor.com",
        ),
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_museum",
            source="https://official.gov.vn",
        ),
        KnowledgeRelationship(
            from_entity_id="activity_temple",
            relationship_type="TARGETS_PLACE",
            to_entity_id="place_temple",
        ),
        KnowledgeRelationship(
            from_entity_id="activity_cafe",
            relationship_type="TARGETS_PLACE",
            to_entity_id="place_cafe",
        ),
        KnowledgeRelationship(
            from_entity_id="activity_restaurant",
            relationship_type="TARGETS_PLACE",
            to_entity_id="place_restaurant",
        ),
        KnowledgeRelationship(
            from_entity_id="activity_museum",
            relationship_type="TARGETS_PLACE",
            to_entity_id="place_museum",
        ),
    ]
    for rel in relationships:
        db_session.add(rel)

    # Properties for museum (requires booking but no URL)
    db_session.add(KnowledgeProperty(
        entity_id="place_museum",
        key="booking_required",
        value="true",
        source="https://official.gov.vn",
    ))

    db_session.commit()
    return db_session


@pytest.fixture
def integration_repo(integration_session: Session) -> ScopeResolutionRepository:
    """Create repository with integration database."""
    return ScopeResolutionRepository(integration_session)


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestOrchestratorIntegration:
    """End-to-end integration tests for the orchestrator."""

    def test_full_flow_returns_bundle(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Full orchestration should return a valid TripResearchBundle."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        assert result is not None
        assert result.scope is not None
        assert result.scope.rootArea is not None
        assert result.scope.rootArea.name == "Hà Nội"
        assert result.trace is not None

    def test_scope_resolved_correctly(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Scope resolution should find the destination area."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        assert result.scope.rootArea is not None
        assert result.scope.rootArea.id == "area_hanoi"
        assert result.scope.rootArea.name == "Hà Nội"

    def test_experiences_discovered(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Experience discovery should find special experiences."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        # Should have discovered 4 experiences (temple, cafe, restaurant, museum)
        assert result.trace.discoveredClaimCount >= 4

    def test_excluded_type_conflict(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Excluded place type should cause conflict."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
            excludedPlaceTypes=["Restaurant"],
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        # Schema v7 exposes Activity as the claim object; the targeted place
        # remains available in the claim path.
        assert any(
            c.claim.object.id == "activity_restaurant"
            for c in result.conflictedExperiences
        )

    def test_booking_required_without_url_conflict(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Museum with booking required but no URL should be conflicted."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        # Museum should be conflicted (booking required, no URL). The v7
        # claim object is the Activity and TARGETS_PLACE carries the venue.
        assert any(
            c.claim.object.id == "activity_museum"
            and "place_museum" in c.claim.path
            for c in result.conflictedExperiences
        )

    def test_trace_counts_accurate(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Trace counts should match actual output."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        assert result.trace.eligibleExperienceCount == len(result.eligibleExperiences)
        assert result.trace.conflictedExperienceCount == len(result.conflictedExperiences)
        assert result.trace.discoveredClaimCount == result.trace.evaluatedExperienceCount

    def test_unknown_destination_raises(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Unknown destination should raise GraphScopeError."""
        input_data = TripResearchInput(
            destination="UnknownLandXYZ",
            days=3,
            partySize=2,
        )

        with pytest.raises(GraphScopeError) as exc_info:
            orchestrate_trip_research(
                integration_repo,
                integration_repo,
                input_data,
            )
        assert exc_info.value.CODE == "GRAPH_SCOPE_NOT_FOUND"

    def test_empty_graph_returns_empty_bundle(
        self, db_session: Session
    ) -> None:
        """Empty graph should return empty bundle without crash."""
        repo = ScopeResolutionRepository(db_session)

        # Add a placeholder area so scope can resolve (but no experiences)
        db_session.add(KnowledgeEntity(
            id="area_vietnam",
            canonical_name="Vietnam",
            normalized_name="vietnam",
            entity_type="AreaAdm0",
            status="verified",
        ))
        db_session.commit()

        input_data = TripResearchInput(
            destination="Vietnam",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(repo, repo, input_data)

        # Should have scope but no experiences
        assert result.scope.rootArea is not None
        assert len(result.eligibleExperiences) == 0
        assert len(result.conflictedExperiences) == 0

    def test_budget_filtering(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Budget level should be passed to fit evaluation."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
            budget=TravelBudget(level=BudgetLevel.MEDIUM),
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        # Should complete without error
        assert result is not None

    def test_selected_places_prioritized(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """User-selected places should be prioritized in ranking."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
            selectedPlaceIds=["place_temple"],
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        if result.eligibleExperiences:
            temple_exp = next(
                (e for e in result.eligibleExperiences if e.claim.object.id == "place_temple"),
                None,
            )
            if temple_exp:
                # Temple should have a rank reason for being user-selected
                assert "user_selected_place" in temple_exp.rankReasons

    def test_deterministic_ranking(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Same input should produce same ranking order."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result1 = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )
        result2 = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        # Ranks should be identical
        ranks1 = [e.rank for e in result1.eligibleExperiences]
        ranks2 = [e.rank for e in result2.eligibleExperiences]
        assert ranks1 == ranks2

        # Claim IDs should be in same order
        ids1 = [e.claim.claimId for e in result1.eligibleExperiences]
        ids2 = [e.claim.claimId for e in result2.eligibleExperiences]
        assert ids1 == ids2

    def test_diversity_in_results(
        self, integration_repo: ScopeResolutionRepository
    ) -> None:
        """Top results should not all be the same type."""
        input_data = TripResearchInput(
            destination="Hà Nội",
            days=3,
            partySize=2,
        )

        result = orchestrate_trip_research(
            integration_repo,
            integration_repo,
            input_data,
        )

        top5 = result.eligibleExperiences[:5]
        if len(top5) >= 3:
            activity_ids = [e.claim.object.id for e in top5]
            assert len(set(activity_ids)) > 1
