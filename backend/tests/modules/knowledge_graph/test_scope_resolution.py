"""Tests for Knowledge Graph research scope resolution.

These tests are standalone and don't require the full app import.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

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


@pytest.fixture
def repo(db_session: Session):
    """Create a ScopeResolutionRepository instance."""
    return ScopeResolutionRepository(db_session)


@pytest.fixture
def populated_db(db_session: Session):
    """Populate database with test data for scope resolution tests."""
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
            id="area_ba_dinh",
            canonical_name="Ba Đình",
            normalized_name="ba dinh",
            entity_type="AreaAdm2",
            status="verified",
        ),
        KnowledgeEntity(
            id="area_legacy",
            canonical_name="Old Area",
            normalized_name="old area",
            entity_type="Area",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_starbucks_hoan_kiem",
            canonical_name="Starbucks Hoàn Kiếm",
            normalized_name="starbucks hoan kiem",
            entity_type="Restaurant",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_temple_of_literature",
            canonical_name="Văn Miếu",
            normalized_name="van mie u",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
    for entity in entities:
        db_session.add(entity)

    aliases = [
        KnowledgeAlias(
            entity_id="area_hanoi",
            alias="Hanoi",
            normalized_alias="hanoi",
            language="en",
        ),
        KnowledgeAlias(
            entity_id="area_hoan_kiem",
            alias="Hoan Kiem",
            normalized_alias="hoan kiem",
            language="en",
        ),
        KnowledgeAlias(
            entity_id="area_hoan_kiem",
            alias="Quận Hoàn Kiếm",
            normalized_alias="quan hoan kiem",
            language="vi",
        ),
    ]
    for alias in aliases:
        db_session.add(alias)

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
            from_entity_id="area_ba_dinh",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ),
        KnowledgeRelationship(
            from_entity_id="place_starbucks_hoan_kiem",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        KnowledgeRelationship(
            from_entity_id="place_temple_of_literature",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
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


class TestGraphStats:
    """Tests for graph statistics."""

    def test_stats_empty(self, repo: ScopeResolutionRepository) -> None:
        """Test stats return zeros for empty graph."""
        stats = repo.stats()
        assert stats.entityCount == 0
        assert stats.aliasCount == 0
        assert stats.relationshipCount == 0
        assert stats.areaCount == 0
        assert stats.areaAdm0Count == 0
        assert stats.areaAdm1Count == 0
        assert stats.areaAdm2Count == 0

    def test_stats_with_data(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test stats return correct counts."""
        stats = populated_repo.stats()
        assert stats.entityCount == 7
        assert stats.aliasCount == 3
        assert stats.relationshipCount == 5
        assert stats.areaAdm0Count == 1
        assert stats.areaAdm1Count == 1
        assert stats.areaAdm2Count == 2
        assert stats.areaCount == 1

    def test_is_empty_true(self, repo: ScopeResolutionRepository) -> None:
        """Test is_empty returns True for empty graph."""
        assert repo.is_empty() is True

    def test_is_empty_false(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test is_empty returns False for populated graph."""
        assert populated_repo.is_empty() is False


class TestAreaResolution:
    """Tests for area resolution by name."""

    def test_resolve_canonical_name(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving area by canonical name."""
        result = populated_repo.resolve_area_by_name("Hà Nội")
        assert result is not None
        assert result.id == "area_hanoi"
        assert result.entity_type == "AreaAdm1"

    def test_resolve_alias(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving area by alias."""
        result = populated_repo.resolve_area_by_name("Hanoi")
        assert result is not None
        assert result.id == "area_hanoi"

    def test_resolve_vietnamese_alias(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving area by Vietnamese alias with diacritics."""
        result = populated_repo.resolve_area_by_name("Quận Hoàn Kiếm")
        assert result is not None
        assert result.id == "area_hoan_kiem"

    def test_resolve_case_insensitive(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving area is case insensitive."""
        result = populated_repo.resolve_area_by_name("hà nội")
        assert result is not None
        assert result.id == "area_hanoi"

    def test_resolve_not_found(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving non-existent area returns None."""
        result = populated_repo.resolve_area_by_name("NonExistentPlace")
        assert result is None

    def test_resolve_non_area_entity_returns_none(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test resolving a Place entity returns None (only Area types allowed)."""
        result = populated_repo.resolve_area_by_name("Starbucks Hoàn Kiếm")
        assert result is None


class TestHierarchyTraversal:
    """Tests for PART_OF hierarchy traversal."""

    def test_traverse_ancestors(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test traversing PART_OF ancestors."""
        ancestors = populated_repo.traverse_part_of_ancestors("area_hoan_kiem", max_depth=4)
        assert len(ancestors) == 2
        assert ancestors[0].id == "area_hanoi"
        assert ancestors[0].depth == 1
        assert ancestors[1].id == "area_vietnam"
        assert ancestors[1].depth == 2

    def test_traverse_ancestors_max_depth(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test ancestor traversal respects max_depth."""
        ancestors = populated_repo.traverse_part_of_ancestors("area_hoan_kiem", max_depth=1)
        assert len(ancestors) == 1
        assert ancestors[0].id == "area_hanoi"

    def test_traverse_descendants(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test traversing PART_OF descendants."""
        descendants = populated_repo.traverse_part_of_descendants("area_hanoi", max_depth=4)
        assert len(descendants) == 2
        descendant_ids = {d.id for d in descendants}
        assert "area_hoan_kiem" in descendant_ids
        assert "area_ba_dinh" in descendant_ids

    def test_traverse_descendants_with_limit(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test descendant traversal respects limit."""
        descendants = populated_repo.traverse_part_of_descendants(
            "area_hanoi", max_depth=4, limit=1
        )
        assert len(descendants) == 1

    def test_traverse_no_descendants(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test traversal of leaf node returns empty list."""
        descendants = populated_repo.traverse_part_of_descendants("area_hoan_kiem", max_depth=4)
        assert len(descendants) == 0


class TestPlaceMapping:
    """Tests for Place to Area mapping via LOCATED_IN."""

    def test_map_single_place_to_area(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test mapping a single place to its area."""
        areas = populated_repo.map_places_to_areas(["place_starbucks_hoan_kiem"])
        assert len(areas) == 1
        assert areas[0].id == "area_hoan_kiem"

    def test_map_multiple_places_same_area(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test mapping multiple places in same area returns unique areas."""
        areas = populated_repo.map_places_to_areas([
            "place_starbucks_hoan_kiem",
            "place_temple_of_literature",
        ])
        assert len(areas) == 1
        assert areas[0].id == "area_hoan_kiem"

    def test_map_empty_place_list(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test mapping empty place list returns empty result."""
        areas = populated_repo.map_places_to_areas([])
        assert len(areas) == 0

    def test_map_place_without_location(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test mapping place without LOCATED_IN relationship returns empty."""
        areas = populated_repo.map_places_to_areas(["area_hanoi"])
        assert len(areas) == 0


class TestScopeResolution:
    """Tests for the kg_resolve_scope tool."""

    def test_resolve_scope_by_canonical_name(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test resolving scope by canonical name."""
        input_data = ScopeResolveInput(destination="Hà Nội")
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is not None
        assert result.rootArea.id == "area_hanoi"
        assert result.rootArea.name == "Hà Nội"
        assert result.rootArea.type == "AreaAdm1"
        assert len(result.ancestors) == 1
        assert result.ancestors[0].id == "area_vietnam"

    def test_resolve_scope_by_alias(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving scope by alias."""
        input_data = ScopeResolveInput(destination="Hanoi")
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is not None
        assert result.rootArea.id == "area_hanoi"

    def test_resolve_scope_normalize_vietnamese(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test resolving scope normalizes Vietnamese diacritics."""
        input_data = ScopeResolveInput(destination="hoan kiem")
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is not None
        assert result.rootArea.id == "area_hoan_kiem"

    def test_resolve_scope_not_found(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving non-existent area returns None root."""
        input_data = ScopeResolveInput(destination="NonExistent")
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is None
        assert result.ancestors == []
        assert result.includedAreas == []

    def test_resolve_scope_includes_descendants(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test scope includes descendant areas."""
        input_data = ScopeResolveInput(destination="Hà Nội")
        result = kg_resolve_scope(populated_repo, input_data)

        assert len(result.includedAreas) == 2
        descendant_ids = {a.id for a in result.includedAreas}
        assert "area_hoan_kiem" in descendant_ids
        assert "area_ba_dinh" in descendant_ids

    def test_resolve_scope_selected_places(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test scope includes areas from selected places."""
        input_data = ScopeResolveInput(
            destination="Vietnam",
            selectedPlaceIds=["place_starbucks_hoan_kiem"],
        )
        result = kg_resolve_scope(populated_repo, input_data)

        assert len(result.selectedPlaceAreas) == 1
        assert result.selectedPlaceAreas[0].id == "area_hoan_kiem"

    def test_resolve_scope_respects_max_depth(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test scope resolution respects maxDepth parameter."""
        input_data = ScopeResolveInput(destination="Hà Nội", maxDepth=1)
        result = kg_resolve_scope(populated_repo, input_data)

        assert len(result.ancestors) == 0
        assert len(result.includedAreas) == 2

    def test_resolve_scope_respects_result_limit(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test scope resolution respects resultLimit parameter."""
        input_data = ScopeResolveInput(destination="Hà Nội", resultLimit=1)
        result = kg_resolve_scope(populated_repo, input_data)

        assert len(result.includedAreas) == 1

    def test_resolve_scope_legacy_area_warning(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test resolving legacy Area type produces warning."""
        input_data = ScopeResolveInput(destination="Old Area")
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is not None
        assert any("LEGACY_AREA_TYPE" in w for w in result.warnings)

    def test_resolve_scope_empty_graph_warning(self, repo: ScopeResolutionRepository) -> None:
        """Test resolving scope on empty graph produces warning."""
        input_data = ScopeResolveInput(destination="Hà Nội")
        result = kg_resolve_scope(repo, input_data)

        assert result.rootArea is None
        assert any("KNOWLEDGE_GRAPH_EMPTY" in w for w in result.warnings)

    def test_resolve_scope_deterministic_ordering(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Test scope results are deterministically ordered."""
        input_data = ScopeResolveInput(destination="Hà Nội")
        result1 = kg_resolve_scope(populated_repo, input_data)
        result2 = kg_resolve_scope(populated_repo, input_data)

        assert [a.id for a in result1.includedAreas] == [a.id for a in result2.includedAreas]
        assert [a.id for a in result1.ancestors] == [a.id for a in result2.ancestors]


class TestScopeResolutionIntegration:
    """Integration tests for scope resolution with CLI-style inputs."""

    def test_resolve_scope_full_hierarchy(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving scope from leaf area includes full hierarchy."""
        input_data = ScopeResolveInput(destination="Hoàn Kiếm", maxDepth=4)
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is not None
        assert result.rootArea.id == "area_hoan_kiem"
        assert len(result.ancestors) == 2
        assert result.ancestors[0].id == "area_hanoi"
        assert result.ancestors[1].id == "area_vietnam"
        assert result.includedAreas == []

    def test_resolve_scope_with_all_parameters(self, populated_repo: ScopeResolutionRepository) -> None:
        """Test resolving scope with all parameters set."""
        input_data = ScopeResolveInput(
            destination="Vietnam",
            selectedPlaceIds=["place_starbucks_hoan_kiem", "place_temple_of_literature"],
            maxDepth=4,
            resultLimit=50,
        )
        result = kg_resolve_scope(populated_repo, input_data)

        assert result.rootArea is not None
        assert result.rootArea.type == "AreaAdm0"
        assert len(result.ancestors) == 0
        assert len(result.includedAreas) == 2
        assert len(result.selectedPlaceAreas) == 1
