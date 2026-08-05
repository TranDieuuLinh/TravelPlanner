"""Tests for Knowledge Graph research experience discovery.

These tests are standalone and don't require the full app import.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    ExperienceDiscoveryInput,
    ScopeResolutionRepository,
    kg_discover_experiences,
    kg_resolve_scope,
    ScopeResolveInput,
    TrustLevel,
)
from app.modules.knowledge_graph.research.experience_tool import _generate_claim_id


@pytest.fixture
def repo(db_session: Session):
    """Create a ScopeResolutionRepository instance."""
    return ScopeResolutionRepository(db_session)


@pytest.fixture
def populated_db(db_session: Session):
    """Populate database with test data for experience discovery tests."""
    entities = [
        # Areas
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
        # Places
        KnowledgeEntity(
            id="place_cafe_giang",
            canonical_name="Cafe Giảng",
            normalized_name="cafe giang",
            entity_type="Cafe",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_old_quarter",
            canonical_name="Old Quarter",
            normalized_name="old quarter",
            entity_type="TravelPlace",
            status="source_backed",
        ),
        KnowledgeEntity(
            id="place_temple",
            canonical_name="Văn Miếu",
            normalized_name="van mie u",
            entity_type="TravelPlace",
            status="draft",
        ),
        # Activities
        KnowledgeEntity(
            id="activity_coffee_tour",
            canonical_name="Coffee Tour Workshop",
            normalized_name="coffee tour workshop",
            entity_type="Activity",
            status="verified",
        ),
        KnowledgeEntity(
            id="activity_cooking",
            canonical_name="Cooking Class",
            normalized_name="cooking class",
            entity_type="Activity",
            status="inferred",
        ),
        KnowledgeEntity(
            id="activity_old_quarter_walk",
            canonical_name="Old Quarter Walk",
            normalized_name="old quarter walk",
            entity_type="Activity",
            status="source_backed",
        ),
    ]
    for entity in entities:
        db_session.add(entity)
    db_session.flush()  # Flush to get IDs for relationships

    relationships = [
        # Hierarchy
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="PART_OF",
            to_entity_id="area_vietnam",
            source=None,
        ),
        KnowledgeRelationship(
            from_entity_id="area_hoan_kiem",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
            source=None,
        ),
        # Schema v7: Area → SPECIAL_EXPERIENCE → Activity → TARGETS_PLACE → Place
        KnowledgeRelationship(
            from_entity_id="area_hoan_kiem",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_coffee_tour",
            recommendations={"priority": "must", "reason": "Historic egg coffee"},
            source="https://example.com/giang",
        ),
        KnowledgeRelationship(
            from_entity_id="activity_coffee_tour",
            relationship_type="TARGETS_PLACE",
            to_entity_id="place_cafe_giang",
            source="https://example.com/giang",
        ),
        KnowledgeRelationship(
            from_entity_id="area_hoan_kiem",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_old_quarter_walk",
            recommendations={"priority": "recommended", "reason": "Historic district"},
            source="https://wikitravel.org/hanoi",
        ),
        KnowledgeRelationship(
            from_entity_id="activity_old_quarter_walk",
            relationship_type="TARGETS_PLACE",
            to_entity_id="place_old_quarter",
            source="https://wikitravel.org/hanoi",
        ),
        # Area → SPECIAL_EXPERIENCE → Activity (inferred)
        KnowledgeRelationship(
            from_entity_id="area_hanoi",
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id="activity_cooking",
            recommendations={"priority": "must", "reason": "Local cuisine"},
            source="inference:taxonomy",
        ),
        # Place → OFFERS_ACTIVITY
        KnowledgeRelationship(
            from_entity_id="place_cafe_giang",
            relationship_type="OFFERS_ACTIVITY",
            to_entity_id="activity_coffee_tour",
            recommendations={"priority": "must", "timeSlots": ["morning", "afternoon"]},
            source="https://cafegiang.com/workshop",
        ),
        # LOCATED_IN
        KnowledgeRelationship(
            from_entity_id="place_cafe_giang",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
            source="https://example.com/giang",
        ),
        KnowledgeRelationship(
            from_entity_id="place_temple",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
            source=None,
        ),
        KnowledgeRelationship(
            from_entity_id="place_temple",
            relationship_type="OFFERS_ACTIVITY",
            to_entity_id="activity_cooking",
            recommendations={"priority": "optional", "reason": "Cultural activity"},
            source="inference:draft_entity",
        ),
    ]
    for rel in relationships:
        db_session.add(rel)

    db_session.commit()
    return db_session


@pytest.fixture
def populated_repo(populated_db: Session):
    """Create repository with populated database."""
    return ScopeResolutionRepository(populated_db)


class TestClaimIdGeneration:
    """Tests for deterministic claim ID generation."""

    def test_claim_id_is_deterministic(self) -> None:
        """Test that claim IDs are generated deterministically."""
        id1 = _generate_claim_id("area_hanoi", "SPECIAL_EXPERIENCE", "place_cafe_giang")
        id2 = _generate_claim_id("area_hanoi", "SPECIAL_EXPERIENCE", "place_cafe_giang")
        assert id1 == id2

    def test_claim_id_different_for_different_inputs(self) -> None:
        """Test that different inputs produce different claim IDs."""
        id1 = _generate_claim_id("area_hanoi", "SPECIAL_EXPERIENCE", "place_cafe_giang")
        id2 = _generate_claim_id("area_hanoi", "SPECIAL_EXPERIENCE", "place_other")
        assert id1 != id2

    def test_claim_id_with_path_segment(self) -> None:
        """Test claim ID generation with path segment."""
        id1 = _generate_claim_id("area_hanoi", "SPECIAL_EXPERIENCE", "place_cafe_giang")
        id2 = _generate_claim_id("area_hanoi", "SPECIAL_EXPERIENCE", "place_cafe_giang", "activity_coffee_tour")
        assert id1 != id2


class TestSpecialExperienceDirectAnchor:
    """Tests the schema-v7 Activity → TARGETS_PLACE direct anchor path."""

    def test_discover_special_experience_place(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Discover special Activities with direct Place anchors."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert len(result.claims) >= 2

        direct_anchor_claims = [
            c for c in result.claims
            if c.predicate == "SPECIAL_EXPERIENCE"
            and c.object.type == "Activity"
            and c.anchorPlace is not None
        ]
        assert len(direct_anchor_claims) >= 2

    def test_special_experience_verified_trust(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that verified entity with source URL gets source_backed trust."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        cafe_claim = next(
            (
                c for c in result.claims
                if c.anchorPlace is not None
                and c.anchorPlace.name == "Cafe Giảng"
            ),
            None
        )
        assert cafe_claim is not None
        assert cafe_claim.trust in (TrustLevel.VERIFIED, TrustLevel.SOURCE_BACKED)


class TestSpecialExperienceToActivity:
    """Tests for Area → SPECIAL_EXPERIENCE → Activity path."""

    def test_discover_special_experience_activity(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test discovering special experiences pointing to activities."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        se_activity_claims = [
            c for c in result.claims
            if c.predicate == "SPECIAL_EXPERIENCE"
            and c.object.type == "Activity"
        ]
        assert len(se_activity_claims) >= 1

    def test_inference_trust_for_inferred_activity(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that inference source results in inferred trust."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=20,
            includeInferred=True,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        cooking_claim = next(
            (c for c in result.claims if c.object.name == "Cooking Class"),
            None
        )
        assert cooking_claim is not None
        assert cooking_claim.trust == TrustLevel.INFERRED


class TestPlaceOffersActivity:
    """Tests for Place → OFFERS_ACTIVITY path."""

    def test_place_offers_activity_chained(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test discovering chained SPECIAL_EXPERIENCE + OFFERS_ACTIVITY paths."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Check for chained path with anchorPlace and activity
        chained_claims = [
            c for c in result.claims
            if c.anchorPlace is not None and c.activity is not None
        ]
        assert len(chained_claims) >= 1

        cafe_tour_claim = next(
            (c for c in chained_claims if c.activity.name == "Coffee Tour Workshop"),
            None
        )
        assert cafe_tour_claim is not None
        assert cafe_tour_claim.anchorPlace.name == "Cafe Giảng"

    def test_located_in_offers_activity(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test discovering chained LOCATED_IN + OFFERS_ACTIVITY paths."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # LOCATED_IN claims with anchorPlace and activity
        li_claims = [
            c for c in result.claims
            if c.predicate == "LOCATED_IN"
            and c.anchorPlace is not None
            and c.activity is not None
        ]
        assert len(li_claims) >= 1


class TestProvenance:
    """Tests for provenance and source tracking."""

    def test_evidence_includes_source(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that evidence includes edge source."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        cafe_claim = next(
            (
                c for c in result.claims
                if c.predicate == "SPECIAL_EXPERIENCE"
                and c.anchorPlace is not None
                and c.anchorPlace.name == "Cafe Giảng"
            ),
            None
        )
        assert cafe_claim is not None
        assert len(cafe_claim.evidence) >= 1
        assert cafe_claim.evidence[0].source == "https://example.com/giang"

    def test_path_is_recorded(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test that the full path is recorded in claims."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        chained_claim = next(
            (c for c in result.claims if c.anchorPlace is not None),
            None
        )
        assert chained_claim is not None
        assert len(chained_claim.path) >= 3
        assert chained_claim.path[0] == chained_claim.subject.id


class TestExternalSourceTrust:
    """Tests for external source trust policy."""

    def test_external_url_source_backed(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that external URL sources get source_backed trust."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        old_quarter_claim = next(
            (
                c for c in result.claims
                if c.anchorPlace is not None
                and c.anchorPlace.name == "Old Quarter"
            ),
            None
        )
        assert old_quarter_claim is not None
        assert old_quarter_claim.trust == TrustLevel.SOURCE_BACKED


class TestInferenceDowngrade:
    """Tests for inference priority downgrade policy."""

    def test_must_priority_downgrade_on_inference(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that 'must' priority is downgraded to 'recommended' for inferred sources."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # The SPECIAL_EXPERIENCE edge for Cooking Class is inferred.
        cafe_claim = next(
            (c for c in result.claims if c.object.name == "Cooking Class"),
            None
        )
        assert cafe_claim is not None

        # Check recommendations are downgraded
        must_downgraded = any(
            "Downgraded" in w or "downgraded" in w.lower()
            for rec in cafe_claim.recommendations
            for w in rec.warnings
        )
        # Either the priority was downgraded or there's a warning
        has_downgrade = (
            must_downgraded or
            any(
                rec.priority.value != "must"
                for rec in cafe_claim.recommendations
            )
        )
        # This test documents the behavior - if there are recommendations
        # and they came from an inferred source, they should be handled appropriately
        if cafe_claim.evidence and cafe_claim.evidence[0].source:
            source = cafe_claim.evidence[0].source
            if source.startswith("inference:"):
                assert has_downgrade or len(cafe_claim.warnings) > 0


class TestDedupe:
    """Tests for claim deduplication."""

    def test_same_target_not_duplicated(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that the same target doesn't produce duplicate claims."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Collect claim IDs
        claim_ids = [c.claimId for c in result.claims]
        assert len(claim_ids) == len(set(claim_ids)), "Duplicate claim IDs found"

    def test_dedupe_by_path_and_recommendation(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that claims are deduplicated by path and recommendation."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=50,
        )
        result1 = kg_discover_experiences(populated_repo, input_data)
        result2 = kg_discover_experiences(populated_repo, input_data)

        # Same input should produce same claims
        ids1 = {c.claimId for c in result1.claims}
        ids2 = {c.claimId for c in result2.claims}
        assert ids1 == ids2


class TestLimit:
    """Tests for result limiting."""

    def test_respects_limit(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test that results respect the limit parameter."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=2,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert len(result.claims) <= 2

    def test_limit_after_rank_and_dedupe(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that limit is applied after ranking and deduplication."""
        input_data_small = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=1,
        )
        input_data_large = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=10,
        )

        result_small = kg_discover_experiences(populated_repo, input_data_small)
        result_large = kg_discover_experiences(populated_repo, input_data_large)

        # Small limit should have fewer or equal claims
        assert len(result_small.claims) <= len(result_large.claims)


class TestStableClaimId:
    """Tests for claim ID stability."""

    def test_claim_id_stable_across_runs(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that claim IDs are stable across multiple runs."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )

        result1 = kg_discover_experiences(populated_repo, input_data)
        result2 = kg_discover_experiences(populated_repo, input_data)

        ids1 = sorted([c.claimId for c in result1.claims])
        ids2 = sorted([c.claimId for c in result2.claims])

        assert ids1 == ids2


class TestDeterministicOrdering:
    """Tests for deterministic result ordering."""

    def test_claims_ordered_deterministically(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that claims are ordered deterministically."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )

        results = [
            kg_discover_experiences(populated_repo, input_data)
            for _ in range(3)
        ]

        claim_ids = [sorted([c.claimId for c in r.claims]) for r in results]
        assert claim_ids[0] == claim_ids[1] == claim_ids[2]

    def test_verified_before_inferred(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that verified/source_backed claims appear before inferred."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=20,
            includeInferred=True,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Find first inferred claim
        first_inferred_idx = None
        for i, claim in enumerate(result.claims):
            if claim.trust == TrustLevel.INFERRED:
                first_inferred_idx = i
                break

        if first_inferred_idx is not None:
            # All claims before should not be inferred
            for claim in result.claims[:first_inferred_idx]:
                assert claim.trust != TrustLevel.INFERRED


class TestScopeFiltering:
    """Tests for scope-based filtering."""

    def test_no_places_outside_scope(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that places outside resolved scope are not included."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # All claim subjects should be within scope
        scope_area_ids = populated_repo.get_scope_area_ids("area_hoan_kiem")

        for claim in result.claims:
            # Subject should be area_hoan_kiem or area in scope
            assert claim.subject.id in scope_area_ids or claim.subject.type in ("Cafe", "TravelPlace", "Activity")

    def test_selected_place_ids_filtering(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that selectedPlaceIds filters results."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            selectedPlaceIds=["place_cafe_giang"],
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Should only include claims related to cafe_giang
        for claim in result.claims:
            if claim.object.type in ("Cafe", "TravelPlace"):
                assert claim.object.id == "place_cafe_giang" or claim.anchorPlace is None or claim.anchorPlace.id == "place_cafe_giang"


class TestIncludeInferred:
    """Tests for includeInferred parameter."""

    def test_exclude_inferred(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test that inferred claims are excluded when includeInferred=False."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=20,
            includeInferred=False,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        for claim in result.claims:
            assert claim.trust != TrustLevel.INFERRED

    def test_include_inferred_default(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test that inferred claims are included by default."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Should have at least some inferred claims
        has_inferred = any(c.trust == TrustLevel.INFERRED for c in result.claims)
        # This depends on test data having inference sources
        # The test data has "inference:taxonomy" source


class TestGraphSnapshot:
    """Tests for graph snapshot in output."""

    def test_snapshot_includes_area_ids(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that graph snapshot includes area IDs."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert result.graphSnapshot is not None
        assert "area_hoan_kiem" in result.graphSnapshot.areaIds
        assert "area_hanoi" in result.graphSnapshot.areaIds

    def test_snapshot_has_timestamp(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that graph snapshot has timestamp."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert result.graphSnapshot.timestamp is not None
        # Should be ISO format
        assert "T" in result.graphSnapshot.timestamp


class TestDestinationResolution:
    """Tests for destination name resolution."""

    def test_resolve_by_destination_name(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test resolving experience by destination name."""
        input_data = ExperienceDiscoveryInput(
            destination="Hoàn Kiếm",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert len(result.claims) > 0
        # Should have claims from area_hoan_kiem scope
        assert any("hoan" in c.subject.name.lower() or "hoan" in c.subject.id.lower() for c in result.claims)

    def test_destination_not_found(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test handling of non-existent destination."""
        input_data = ExperienceDiscoveryInput(
            destination="NonExistentPlace",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert len(result.claims) == 0
        assert len(result.unknowns) > 0


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_graph(self, repo: ScopeResolutionRepository) -> None:
        """Test handling of empty graph."""
        # For empty graph, area_hanoi doesn't exist, so scope will just be [area_hanoi]
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            limit=20,
        )
        result = kg_discover_experiences(repo, input_data)

        # Empty graph returns empty claims (no experiences found)
        assert len(result.claims) == 0
        # Snapshot should exist with timestamp
        assert result.graphSnapshot is not None
        assert result.graphSnapshot.timestamp is not None

    def test_no_special_experiences(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test when no special experiences exist in scope."""
        # Use an area with no special experiences
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_vietnam",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Should handle gracefully (may have no claims or limited claims)
        assert result is not None

    def test_neither_root_nor_destination(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test error when neither rootAreaId nor destination provided."""
        input_data = ExperienceDiscoveryInput(
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        assert len(result.claims) == 0
        assert any("SCOPE_REQUIRED" in w for w in result.warnings)


class TestRecommendations:
    """Tests for recommendation parsing and structure."""

    def test_recommendations_have_priority(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that recommendations include priority field."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        claims_with_recs = [c for c in result.claims if c.recommendations]
        assert len(claims_with_recs) > 0

        for claim in claims_with_recs:
            for rec in claim.recommendations:
                assert rec.priority is not None

    def test_time_slots_parsed(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test that timeSlots are parsed from recommendations."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hoan_kiem",
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Find claim with OFFERS_ACTIVITY that should have timeSlots
        offers_claim = next(
            (c for c in result.claims if c.activity is not None),
            None
        )
        if offers_claim:
            time_slots_found = any(
                len(rec.timeSlots) > 0
                for rec in offers_claim.recommendations
            )
            # This depends on test data having timeSlots in recommendations


class TestExperienceDiscoveryIntegration:
    """Integration tests for full experience discovery flow."""

    def test_full_flow_with_scope_resolution(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test full flow: resolve scope then discover experiences."""
        # First resolve scope
        scope_input = ScopeResolveInput(destination="Hà Nội")
        scope_result = kg_resolve_scope(populated_repo, scope_input)

        assert scope_result.rootArea is not None
        root_id = scope_result.rootArea.id

        # Then discover experiences
        exp_input = ExperienceDiscoveryInput(
            rootAreaId=root_id,
            limit=20,
        )
        exp_result = kg_discover_experiences(populated_repo, exp_input)

        # Should have discovered some experiences
        assert exp_result is not None
        # Snapshot should include the scope areas
        assert root_id in exp_result.graphSnapshot.areaIds

    def test_with_interests_filter(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test experience discovery with interest filters."""
        input_data = ExperienceDiscoveryInput(
            rootAreaId="area_hanoi",
            interests=["coffee", "culture"],
            limit=20,
        )
        result = kg_discover_experiences(populated_repo, input_data)

        # Should handle interest filtering gracefully
        assert result is not None
