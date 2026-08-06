"""Tests for Knowledge Graph experience fit evaluation tool.

These tests are standalone and don't require the full app import.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research import (
    BudgetLevel,
    CheckStatus,
    ExperienceFitInput,
    ExperienceFitOutput,
    ScopeResolutionRepository,
    TransportMode,
    kg_evaluate_experience_fit,
)
from app.modules.knowledge_graph.research.experience_fit_tool import (
    EntityNotFoundError,
    HARD_CONSTRAINTS,
    _compute_overall_status,
    _is_verified_source,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def repo(db_session: Session) -> ScopeResolutionRepository:
    """Create a ScopeResolutionRepository instance."""
    return ScopeResolutionRepository(db_session)


@pytest.fixture
def populated_db(db_session: Session) -> Session:
    """Populate database with test data for experience fit evaluation.

    Creates a mini graph:
    - area_vietnam (AreaAdm0)
    - area_hanoi (AreaAdm1) -> area_vietnam
    - area_hoan_kiem (AreaAdm2) -> area_hanoi
    - area_sa_pa (AreaAdm2) -> area_hanoi (outside hoan kiem scope)
    - place_hoan_kiem_temple (TravelPlace) -> area_hoan_kiem
    - place_restaurant_hoan_kiem (Restaurant) -> area_hoan_kiem
    - place_outside (TravelPlace) -> area_sa_pa
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
            id="area_sa_pa",
            canonical_name="Sa Pa",
            normalized_name="sa pa",
            entity_type="AreaAdm2",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_hoan_kiem_temple",
            canonical_name="Văn Miếu Quốc Tử Giám",
            normalized_name="van mieu quoc tu giam",
            entity_type="TravelPlace",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_restaurant_hoan_kiem",
            canonical_name="Restaurant A",
            normalized_name="restaurant a",
            entity_type="Restaurant",
            status="verified",
        ),
        KnowledgeEntity(
            id="place_outside",
            canonical_name="Sapa Terraced Fields",
            normalized_name="sapa terraced fields",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
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
            from_entity_id="area_sa_pa",
            relationship_type="PART_OF",
            to_entity_id="area_hanoi",
        ),
        KnowledgeRelationship(
            from_entity_id="place_hoan_kiem_temple",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        KnowledgeRelationship(
            from_entity_id="place_restaurant_hoan_kiem",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
        KnowledgeRelationship(
            from_entity_id="place_outside",
            relationship_type="LOCATED_IN",
            to_entity_id="area_sa_pa",
        ),
    ]
    for rel in relationships:
        db_session.add(rel)

    db_session.commit()
    return db_session


@pytest.fixture
def populated_repo(populated_db: Session) -> ScopeResolutionRepository:
    """Create repository with populated database."""
    return ScopeResolutionRepository(populated_db)


@pytest.fixture
def entity_with_all_props(db_session: Session) -> ScopeResolutionRepository:
    """Populate database with entity that has all relevant properties."""
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
            normalized_name="van mie u",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
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
    ]
    for rel in relationships:
        db_session.add(rel)

    properties = [
        KnowledgeProperty(
            entity_id="place_temple",
            key="opening_hours",
            value="07:00-18:00",
            source="https://wikipedia.org",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="admission_price",
            value='{"currency":"VND","representativeAmount":30000}',
            source="https://vietnamtourism.gov.vn",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="typical_duration_minutes",
            value="120",
            source="https://wikipedia.org",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="best_time_slots",
            value="morning,afternoon",
            source="https://vietnamtourism.gov.vn",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="booking_required",
            value="false",
            source="https://vietnamtourism.gov.vn",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="accessibility_features",
            value="wheelchair,hearing_loop",
            source="https://official.gov.vn",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="suitable_for",
            value="solo,group,family",
            source="https://vietnamtourism.gov.vn",
        ),
        KnowledgeProperty(
            entity_id="place_temple",
            key="weather_constraints",
            value="avoid monsoon season",
            source="https://vietnamtourism.gov.vn",
        ),
    ]
    for prop in properties:
        db_session.add(prop)

    db_session.commit()
    return ScopeResolutionRepository(db_session)


@pytest.fixture
def entity_with_booking_required(db_session: Session) -> ScopeResolutionRepository:
    """Entity that requires booking but has no booking URL."""
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
            id="place_museum",
            canonical_name="National Museum",
            normalized_name="national museum",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
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
            from_entity_id="place_museum",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
    ]
    for rel in relationships:
        db_session.add(rel)

    properties = [
        KnowledgeProperty(
            entity_id="place_museum",
            key="booking_required",
            value="true",
            source="https://official.gov.vn",
        ),
    ]
    for prop in properties:
        db_session.add(prop)

    db_session.commit()
    return ScopeResolutionRepository(db_session)


@pytest.fixture
def entity_with_booking_url(db_session: Session) -> ScopeResolutionRepository:
    """Entity that requires booking AND has a booking URL."""
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
            id="place_theater",
            canonical_name="Water Puppet Theater",
            normalized_name="water puppet theater",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
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
            from_entity_id="place_theater",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
    ]
    for rel in relationships:
        db_session.add(rel)

    properties = [
        KnowledgeProperty(
            entity_id="place_theater",
            key="booking_required",
            value="true",
            source="https://booking.com",
        ),
        KnowledgeProperty(
            entity_id="place_theater",
            key="booking_url",
            value="https://ticket.vn/theater",
            source="https://booking.com",
        ),
    ]
    for prop in properties:
        db_session.add(prop)

    db_session.commit()
    return ScopeResolutionRepository(db_session)


@pytest.fixture
def entity_unverified_source(db_session: Session) -> ScopeResolutionRepository:
    """Entity with unverified (AI-inferred) opening hours."""
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
            id="place_mystery",
            canonical_name="Mystery Place",
            normalized_name="mystery place",
            entity_type="TravelPlace",
            status="verified",
        ),
    ]
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
            from_entity_id="place_mystery",
            relationship_type="LOCATED_IN",
            to_entity_id="area_hoan_kiem",
        ),
    ]
    for rel in relationships:
        db_session.add(rel)

    properties = [
        KnowledgeProperty(
            entity_id="place_mystery",
            key="opening_hours",
            value="09:00-17:00",
            source=None,
        ),
    ]
    for prop in properties:
        db_session.add(prop)

    db_session.commit()
    return ScopeResolutionRepository(db_session)


# ---------------------------------------------------------------------------
# Provenance helper tests
# ---------------------------------------------------------------------------

class TestIsVerifiedSource:
    """Tests for source verification logic."""

    def test_verified_official(self) -> None:
        assert _is_verified_source("https://official.gov.vn") is True

    def test_verified_wikipedia(self) -> None:
        assert _is_verified_source("https://wikipedia.org") is True

    def test_verified_booking(self) -> None:
        assert _is_verified_source("https://booking.com") is True

    def test_verified_agoda(self) -> None:
        assert _is_verified_source("https://agoda.com") is True

    def test_verified_tripadvisor(self) -> None:
        assert _is_verified_source("https://tripadvisor.com") is True

    def test_unverified_none(self) -> None:
        assert _is_verified_source(None) is False

    def test_unverified_ai_inferred(self) -> None:
        assert _is_verified_source("ai-inferred") is False

    def test_unverified_unknown(self) -> None:
        assert _is_verified_source("some random source") is False


# ---------------------------------------------------------------------------
# Overall status computation tests
# ---------------------------------------------------------------------------

class TestComputeOverallStatus:
    """Tests for overall status computation."""

    def test_all_supported(self) -> None:
        checks = [
            DimensionCheck(dimension="opening_hours", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="admission_fee", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
        ]
        assert _compute_overall_status(checks) == CheckStatus.SUPPORTED

    def test_hard_constraint_conflict_wins(self) -> None:
        """Any hard constraint conflicted should override supported checks."""
        from app.modules.knowledge_graph.research.schema import DimensionCheck
        checks = [
            DimensionCheck(dimension="geographic_scope", status=CheckStatus.CONFLICTED, reason="outside", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="opening_hours", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="admission_fee", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
        ]
        assert _compute_overall_status(checks) == CheckStatus.CONFLICTED

    def test_excluded_type_conflict_wins(self) -> None:
        """excluded_type is a hard constraint."""
        from app.modules.knowledge_graph.research.schema import DimensionCheck
        checks = [
            DimensionCheck(dimension="excluded_type", status=CheckStatus.CONFLICTED, reason="excluded", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="opening_hours", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
        ]
        assert _compute_overall_status(checks) == CheckStatus.CONFLICTED

    def test_no_conflict_but_critical_unknown(self) -> None:
        """No conflicts but critical dimension unknown -> overall unknown."""
        from app.modules.knowledge_graph.research.schema import DimensionCheck
        checks = [
            DimensionCheck(dimension="geographic_scope", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="opening_hours", status=CheckStatus.UNKNOWN, reason="no data", evidenceClaimIds=[], sources=[]),
        ]
        assert _compute_overall_status(checks) == CheckStatus.UNKNOWN

    def test_non_critical_unknown_is_supported(self) -> None:
        """Unknown in non-hard constraint with no conflicts -> supported."""
        from app.modules.knowledge_graph.research.schema import DimensionCheck
        checks = [
            DimensionCheck(dimension="geographic_scope", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="excluded_type", status=CheckStatus.SUPPORTED, reason="ok", evidenceClaimIds=[], sources=[]),
            DimensionCheck(dimension="weather_constraints", status=CheckStatus.UNKNOWN, reason="no data", evidenceClaimIds=[], sources=[]),
        ]
        assert _compute_overall_status(checks) == CheckStatus.SUPPORTED


# ---------------------------------------------------------------------------
# Input validation tests
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Tests for ExperienceFitInput validation."""

    def test_requires_entity_or_claim(self, repo: ScopeResolutionRepository) -> None:
        """Must provide either entityId or claimId."""
        with pytest.raises(ValueError, match="entityId or claimId"):
            input_data = ExperienceFitInput(
                destination="Hà Nội",
                days=3,
                partySize=2,
            )
            kg_evaluate_experience_fit(repo, input_data)

    def test_cannot_provide_both(self, repo: ScopeResolutionRepository) -> None:
        """Cannot provide both entityId and claimId."""
        with pytest.raises(ValueError, match="not both"):
            input_data = ExperienceFitInput(
                entityId="place_temple",
                claimId="claim_123",
                destination="Hà Nội",
                days=3,
                partySize=2,
            )
            kg_evaluate_experience_fit(repo, input_data)

    def test_entity_not_found_error(self, repo: ScopeResolutionRepository) -> None:
        """Non-existent entity raises clear error."""
        with pytest.raises(EntityNotFoundError) as exc_info:
            input_data = ExperienceFitInput(
                entityId="nonexistent_entity",
                destination="Hà Nội",
                days=3,
                partySize=2,
            )
            kg_evaluate_experience_fit(repo, input_data)
        assert "nonexistent_entity" in str(exc_info.value)
        assert "not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Dimension check tests
# ---------------------------------------------------------------------------

class TestExcludedType:
    """Tests for excluded_type dimension."""

    def test_excluded_type_conflicted(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Restaurant type excluded -> conflicted."""
        input_data = ExperienceFitInput(
            entityId="place_restaurant_hoan_kiem",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            excludedPlaceTypes=["Restaurant"],
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "excluded_type")
        assert check.status == CheckStatus.CONFLICTED
        assert "Restaurant" in check.reason

    def test_type_not_excluded_supported(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Type not in exclusion list -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_hoan_kiem_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            excludedPlaceTypes=["Restaurant"],
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "excluded_type")
        assert check.status == CheckStatus.SUPPORTED

    def test_no_exclusions_supported(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """No exclusion list -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_restaurant_hoan_kiem",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "excluded_type")
        assert check.status == CheckStatus.SUPPORTED


class TestGeographicScope:
    """Tests for geographic_scope dimension."""

    def test_entity_in_scope_supported(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Entity within scope -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_hoan_kiem_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "geographic_scope")
        assert check.status == CheckStatus.SUPPORTED

    def test_entity_outside_scope_conflicted(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Entity outside scope -> conflicted."""
        input_data = ExperienceFitInput(
            entityId="place_outside",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "geographic_scope")
        assert check.status == CheckStatus.CONFLICTED

    def test_unknown_destination_unknown(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Cannot resolve destination -> unknown."""
        input_data = ExperienceFitInput(
            entityId="place_hoan_kiem_temple",
            destination="UnknownLand",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "geographic_scope")
        assert check.status == CheckStatus.UNKNOWN


class TestOpeningHours:
    """Tests for opening_hours dimension."""

    def test_verified_opening_hours_supported(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Verified opening hours -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        check = next(c for c in result.checks if c.dimension == "opening_hours")
        assert check.status == CheckStatus.SUPPORTED

    def test_missing_opening_hours_unknown(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Missing opening hours -> unknown (never supported)."""
        input_data = ExperienceFitInput(
            entityId="place_hoan_kiem_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        check = next(c for c in result.checks if c.dimension == "opening_hours")
        assert check.status == CheckStatus.UNKNOWN

    def test_unverified_source_unknown(
        self, entity_unverified_source: ScopeResolutionRepository
    ) -> None:
        """Unverified (AI-inferred) source -> unknown."""
        input_data = ExperienceFitInput(
            entityId="place_mystery",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_unverified_source, input_data)
        check = next(c for c in result.checks if c.dimension == "opening_hours")
        assert check.status == CheckStatus.UNKNOWN
        assert "not verified" in check.reason.lower() or "inferred" in check.reason.lower()


class TestBookingRequired:
    """Tests for booking_required dimension."""

    def test_booking_required_with_url_supported(
        self, entity_with_booking_url: ScopeResolutionRepository
    ) -> None:
        """Booking required with URL -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_theater",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_booking_url, input_data)
        check = next(c for c in result.checks if c.dimension == "booking_required")
        assert check.status == CheckStatus.SUPPORTED
        assert "booking URL" in check.reason

    def test_booking_required_without_url_conflicted(
        self, entity_with_booking_required: ScopeResolutionRepository
    ) -> None:
        """Booking required but no URL -> conflicted (hard constraint)."""
        input_data = ExperienceFitInput(
            entityId="place_museum",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_booking_required, input_data)
        check = next(c for c in result.checks if c.dimension == "booking_required")
        assert check.status == CheckStatus.CONFLICTED
        assert result.overallStatus == CheckStatus.CONFLICTED


class TestAdmissionFee:
    """Tests for admission_fee dimension."""

    def test_fee_within_budget_supported(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Fee within budget -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            budgetTargetAmount=100000,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        check = next(c for c in result.checks if c.dimension == "admission_fee")
        assert check.status == CheckStatus.SUPPORTED

    def test_fee_exceeds_budget_conflicted(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Fee exceeds budget -> conflicted."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            budgetTargetAmount=10000,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        check = next(c for c in result.checks if c.dimension == "admission_fee")
        assert check.status == CheckStatus.CONFLICTED


class TestAccessibility:
    """Tests for accessibility dimension."""

    def test_all_features_available_supported(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """All required features available -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            accessibilityRequirements=["wheelchair"],
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        check = next(c for c in result.checks if c.dimension == "accessibility")
        assert check.status == CheckStatus.SUPPORTED

    def test_missing_features_conflicted(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Required feature missing -> conflicted."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            accessibilityRequirements=["wheelchair", "guide_dog"],
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        check = next(c for c in result.checks if c.dimension == "accessibility")
        assert check.status == CheckStatus.CONFLICTED
        assert "guide_dog" in check.reason

    def test_no_requirements_supported(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """No accessibility requirements -> supported."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        check = next(c for c in result.checks if c.dimension == "accessibility")
        assert check.status == CheckStatus.SUPPORTED


# ---------------------------------------------------------------------------
# Overall result tests
# ---------------------------------------------------------------------------

class TestOverallResult:
    """Tests for overall status computation in context."""

    def test_hard_conflict_overrides_supported(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Hard constraint conflict overrides all supported checks."""
        input_data = ExperienceFitInput(
            entityId="place_outside",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        assert result.overallStatus == CheckStatus.CONFLICTED

    def test_entity_not_found_clear_error(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """Non-existent entity returns clear error."""
        with pytest.raises(EntityNotFoundError):
            input_data = ExperienceFitInput(
                entityId="totally_fake_entity",
                destination="Hà Nội",
                days=3,
                partySize=2,
            )
            kg_evaluate_experience_fit(populated_repo, input_data)


class TestDeterministicOutput:
    """Tests for deterministic output."""

    def test_checks_are_sorted(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Dimension checks are always sorted alphabetically."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result1 = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        result2 = kg_evaluate_experience_fit(entity_with_all_props, input_data)

        dims1 = [c.dimension for c in result1.checks]
        dims2 = [c.dimension for c in result2.checks]
        assert dims1 == dims2
        assert dims1 == sorted(dims1)

    def test_same_input_same_output(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Same input always produces identical output."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
            accessibilityRequirements=["wheelchair"],
        )
        result1 = kg_evaluate_experience_fit(entity_with_all_props, input_data)
        result2 = kg_evaluate_experience_fit(entity_with_all_props, input_data)

        assert result1.overallStatus == result2.overallStatus
        assert len(result1.checks) == len(result2.checks)
        for c1, c2 in zip(result1.checks, result2.checks):
            assert c1.dimension == c2.dimension
            assert c1.status == c2.status
            assert c1.reason == c2.reason


class TestOutputSchema:
    """Tests for output schema correctness."""

    def test_output_has_required_fields(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Output contains all required fields."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)

        assert isinstance(result, ExperienceFitOutput)
        assert result.entity is not None
        assert result.entity.id == "place_temple"
        assert result.entity.name == "Văn Miếu"
        assert result.entity.type == "TravelPlace"
        assert result.overallStatus in list(CheckStatus)
        assert isinstance(result.checks, list)
        assert isinstance(result.warnings, list)

    def test_each_check_has_required_fields(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """Each dimension check has all required fields."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)

        for check in result.checks:
            assert check.dimension
            assert check.status in list(CheckStatus)
            assert check.reason
            assert isinstance(check.evidenceClaimIds, list)
            assert isinstance(check.sources, list)

    def test_all_dimensions_present(
        self, entity_with_all_props: ScopeResolutionRepository
    ) -> None:
        """All expected dimensions are evaluated."""
        input_data = ExperienceFitInput(
            entityId="place_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(entity_with_all_props, input_data)

        expected_dimensions = {
            "geographic_scope",
            "excluded_type",
            "opening_hours",
            "typical_duration",
            "time_slot",
            "booking_required",
            "admission_fee",
            "accessibility",
            "suitable_for",
            "requirements",
            "weather_constraints",
            "provenance_trust",
        }
        actual_dimensions = {c.dimension for c in result.checks}
        assert actual_dimensions == expected_dimensions


class TestClaimIdSupport:
    """Tests for claimId as alternative to entityId."""

    def test_claim_id_works(
        self, populated_repo: ScopeResolutionRepository
    ) -> None:
        """claimId can be used instead of entityId."""
        input_data = ExperienceFitInput(
            claimId="place_hoan_kiem_temple",
            destination="Hoàn Kiếm",
            days=3,
            partySize=2,
        )
        result = kg_evaluate_experience_fit(populated_repo, input_data)
        assert result.entity is not None
        assert result.entity.id == "place_hoan_kiem_temple"
