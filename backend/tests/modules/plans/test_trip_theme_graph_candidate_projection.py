"""Tests for the graph candidate projection adapter.

Scope (MICRO-TASK 5.3):
- Only ``TripResearchBundle.eligibleExperiences`` is projected.
- Conflicted experiences are excluded; unknown-fit evidence remains selectable.
- The three supported graph shapes are correctly identified.
- Claims with the same Activity (or Place) are grouped.
- Deduplication is deterministic (tie-break by claimId).
- ``conflictedExperiences`` and ``unknowns`` lists are not consulted.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.modules.knowledge_graph.research import (
    CheckStatus,
    ConflictedExperience,
    FitResult,
    GraphEvidenceClaim,
    GraphSnapshot,
    RankedExperience,
    TrustLevel,
    TripResearchBundle,
)
from app.modules.knowledge_graph.research.schema import (
    EdgeEvidence,
    EntitySummary,
    Recommendation,
    RecommendationPriority,
    ScopeResolveOutput,
)
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    GraphCandidateCatalog,
    GraphExperienceCandidate,
    _claim_shape,
    infer_experience_category,
    _is_selectable,
    build_graph_candidate_catalog,
    project_graph_candidate_catalog,
)


def test_category_inference_separates_food_culture_and_nightlife() -> None:
    assert infer_experience_category(activity_name="Museum history tour").value == "culture"
    assert infer_experience_category(activity_name="Bun cha restaurant").value == "food"
    assert infer_experience_category(activity_name="Hanoi bar crawl").value == "nightlife"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fit(supported: bool = True, has_hard_conflict: bool = False) -> FitResult:
    return FitResult(
        status=CheckStatus.SUPPORTED if supported else CheckStatus.CONFLICTED,
        hasHardConflict=has_hard_conflict,
        dimensionCount=2,
    )


def _entity(
    entity_id: str,
    name: str,
    entity_type: str,
    status: str = "verified",
) -> EntitySummary:
    return EntitySummary(id=entity_id, name=name, type=entity_type, status=status)


def _claim(
    claim_id: str,
    predicate: str,
    subject_id: str,
    object_id: str,
    object_type: str,
    object_name: str = "Test Place",
    object_status: str = "verified",
    trust: TrustLevel = TrustLevel.SOURCE_BACKED,
    activity_id: str | None = None,
    activity_type: str | None = None,
    activity_name: str | None = None,
    anchor_place_id: str | None = None,
    anchor_place_name: str = "Anchor Place",
    anchor_place_type: str = "TravelPlace",
    priority: RecommendationPriority = RecommendationPriority.RECOMMENDED,
    source: str | None = "https://example.com",
    recommendations: list[Recommendation] | None = None,
) -> GraphEvidenceClaim:
    activity: EntitySummary | None = None
    if activity_id is not None:
        activity = _entity(activity_id, activity_name or activity_id, activity_type or "Activity")

    anchor_place: EntitySummary | None = None
    if anchor_place_id is not None or predicate in ("OFFERS_ACTIVITY", "LOCATED_IN"):
        anchor_place = _entity(
            anchor_place_id or subject_id,
            anchor_place_name,
            anchor_place_type,
        )

    path = [subject_id, predicate, object_id]
    if predicate == "SPECIAL_EXPERIENCE" and anchor_place is not None:
        path.extend(["TARGETS_PLACE", anchor_place.id])
    if predicate in ("OFFERS_ACTIVITY", "LOCATED_IN"):
        path = [subject_id, predicate, object_id, "OFFERS_ACTIVITY", activity_id or object_id]
        if anchor_place:
            path = [subject_id, predicate, anchor_place_id or subject_id, "OFFERS_ACTIVITY", activity_id or object_id]

    return GraphEvidenceClaim(
        claimId=claim_id,
        subject=_entity(subject_id, "Area Hanoi", "AreaAdm1"),
        predicate=predicate,
        object=_entity(object_id, object_name, object_type, object_status),
        path=path,
        anchorPlace=anchor_place,
        activity=activity,
        recommendations=recommendations or [Recommendation(priority=priority)],
        evidence=[
            EdgeEvidence(source=source, recommendations=recommendations or [])
        ],
        trust=trust,
    )


def _ranked(
    claim_id: str,
    rank: int,
    predicate: str,
    subject_id: str = "area_hanoi",
    object_id: str | None = None,
    object_type: str = "TravelPlace",
    object_name: str = "Test Place",
    supported: bool = True,
    has_hard_conflict: bool = False,
    **claim_kwargs: Any,
) -> RankedExperience:
    obj_id = object_id or claim_id
    return RankedExperience(
        claim=_claim(
            claim_id=claim_id,
            predicate=predicate,
            subject_id=subject_id,
            object_id=obj_id,
            object_type=object_type,
            object_name=object_name,
            **claim_kwargs,
        ),
        fit=_fit(supported=supported, has_hard_conflict=has_hard_conflict),
        rank=rank,
        rankReasons=[f"rank_{rank}"],
    )


def _bundle(
    eligible: list[RankedExperience],
    conflicted: list[RankedExperience] | None = None,
    unknowns: list | None = None,
) -> TripResearchBundle:
    converted_conflicted = [
        ConflictedExperience(
            claim=item.claim,
            fit=item.fit,
            conflictReasons=["hard_conflict"],
        )
        for item in (conflicted or [])
    ]
    return TripResearchBundle(
        scope=ScopeResolveOutput(),
        eligibleExperiences=eligible,
        conflictedExperiences=converted_conflicted,
        unknowns=unknowns or [],
        graphSnapshot=GraphSnapshot(timestamp="2026-08-04T00:00:00Z"),
    )


# ---------------------------------------------------------------------------
# Catalog entry point
# ---------------------------------------------------------------------------


class TestProjectCatalogEntryPoint:
    """``project_graph_candidate_catalog`` is the primary public API."""

    def test_returns_graph_candidate_catalog_instance(self) -> None:
        result = project_graph_candidate_catalog(_bundle([]))
        assert isinstance(result, GraphCandidateCatalog)

    def test_returns_graph_candidate_catalog_from_alias(self) -> None:
        assert build_graph_candidate_catalog is project_graph_candidate_catalog


# ---------------------------------------------------------------------------
# Exclusion: conflicted experiences
# ---------------------------------------------------------------------------


class TestConflictedExcluded:
    """Conflicted experiences do not appear in the selectable catalog."""

    def test_conflicted_fit_excluded(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="place_a",
            object_type="TravelPlace",
            supported=False,
            has_hard_conflict=True,
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[], conflicted=[ranked]))
        assert len(catalog.candidates) == 0

    def test_unknown_fit_is_selectable_without_hard_conflict(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_a",
            object_type="Activity",
            supported=False,
        )
        ranked = ranked.model_copy(
            update={
                "fit": FitResult(
                    status=CheckStatus.UNKNOWN,
                    hasHardConflict=False,
                    dimensionCount=0,
                )
            }
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert len(catalog.candidates) == 1

    def test_conflicted_experiences_in_bundle_do_not_affect_output(self) -> None:
        conflicted = _ranked(
            "c_conflict",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="place_conflict",
            object_type="TravelPlace",
            supported=False,
            has_hard_conflict=True,
        )
        eligible = _ranked(
            "c_eligible",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_eligible",
            object_type="Activity",
            activity_id="activity_eligible",
        )
        catalog = project_graph_candidate_catalog(
            _bundle(eligible=[eligible], conflicted=[conflicted])
        )
        assert len(catalog.candidates) == 1
        assert catalog.candidates[0].claim_ids == ["c_eligible"]


# ---------------------------------------------------------------------------
# Exclusion: unsupported predicate shapes
# ---------------------------------------------------------------------------


class TestUnsupportedShapesExcluded:
    """Predicate shapes not in the supported set are excluded."""

    @pytest.mark.parametrize(
        "predicate",
        [
            "PART_OF",
            "NEARBY",
            "NEIGHBOR_OF",
            "RELATED_TO",
            "ALIAS_OF",
        ],
    )
    def test_unsupported_predicate_excluded(self, predicate: str) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate=predicate,
            object_id="entity_x",
            object_type="Area",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert len(catalog.candidates) == 0


# ---------------------------------------------------------------------------
# Inclusion: supported shapes
# ---------------------------------------------------------------------------


class TestSupportedShapeInclusion:
    """All three explicitly supported graph shapes are admitted."""

    def test_special_experience_direct_anchor_included(self) -> None:
        ranked = _ranked(
            "c_se_anchor",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_walk",
            object_type="Activity",
            object_name="Đi dạo Hồ Gươm",
            activity_id="activity_walk",
            activity_name="Đi dạo Hồ Gươm",
            anchor_place_id="place_hoan_kiem",
            trust=TrustLevel.SOURCE_BACKED,
            priority=RecommendationPriority.MUST,
            source="https://example.com/cafe",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert len(catalog.candidates) == 1
        candidate = catalog.candidates[0]
        assert candidate.place_ids == ["place_hoan_kiem"]
        assert candidate.activity_id == "activity_walk"
        assert candidate.activity_name == "Đi dạo Hồ Gươm"
        assert candidate.anchor_place_ids == ["place_hoan_kiem"]
        assert candidate.anchor_place_names == {
            "place_hoan_kiem": "Anchor Place"
        }
        assert candidate.is_special_experience is True
        assert candidate.claim_ids == ["c_se_anchor"]
        assert candidate.trust is TrustLevel.SOURCE_BACKED
        assert candidate.recommendation is not None
        assert candidate.recommendation.priority is RecommendationPriority.MUST
        assert candidate.source_refs == ["https://example.com/cafe"]

    def test_special_experience_activity_included(self) -> None:
        ranked = _ranked(
            "c_se_activity",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            object_name="Cooking Class",
            activity_id="activity_cooking",
            activity_type="Activity",
            activity_name="Cooking Class",
            priority=RecommendationPriority.RECOMMENDED,
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert len(catalog.candidates) == 1
        candidate = catalog.candidates[0]
        assert candidate.activity_id == "activity_cooking"
        assert candidate.place_ids == []

    def test_offers_activity_without_special_seed_is_excluded(self) -> None:
        ranked = _ranked(
            "c_offers",
            rank=1,
            predicate="OFFERS_ACTIVITY",
            subject_id="place_cafe",
            object_id="activity_coffee_tour",
            object_type="Activity",
            object_name="Coffee Tour",
            activity_id="activity_coffee_tour",
            activity_type="Activity",
            activity_name="Coffee Tour",
            anchor_place_id="place_cafe",
            anchor_place_name="Cafe Giảng",
            priority=RecommendationPriority.MUST,
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates == []

    def test_located_in_offer_without_special_seed_is_excluded(self) -> None:
        ranked = _ranked(
            "c_located_offers",
            rank=1,
            predicate="LOCATED_IN",
            subject_id="area_hoan_kiem",
            object_id="place_restaurant",
            object_type="Restaurant",
            object_name="Bun Cha",
            activity_id="activity_bun_cha",
            activity_type="Activity",
            activity_name="Eat Bun Cha",
            anchor_place_id="place_restaurant",
            anchor_place_name="Bun Cha Place",
            priority=RecommendationPriority.RECOMMENDED,
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates == []


# ---------------------------------------------------------------------------
# Grouping by Activity
# ---------------------------------------------------------------------------


class TestActivityGrouping:
    """Claims with the same Activity ID are merged into one candidate."""

    def test_two_places_offering_same_activity_grouped(self) -> None:
        special_rank = _ranked(
            "c_special",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_coffee_tour",
            object_type="Activity",
            object_name="Coffee Tour",
            activity_id="activity_coffee_tour",
            activity_name="Coffee Tour",
        )
        cafe_rank = _ranked(
            "c_cafe",
            rank=2,
            predicate="OFFERS_ACTIVITY",
            subject_id="place_cafe_giang",
            object_id="activity_coffee_tour",
            object_type="Activity",
            object_name="Coffee Tour",
            activity_id="activity_coffee_tour",
            anchor_place_id="place_cafe_giang",
            anchor_place_name="Cafe Giang",
        )
        restaurant_rank = _ranked(
            "c_restaurant",
            rank=3,
            predicate="OFFERS_ACTIVITY",
            subject_id="place_restaurant",
            object_id="activity_coffee_tour",
            object_type="Activity",
            object_name="Coffee Tour",
            activity_id="activity_coffee_tour",
            anchor_place_id="place_restaurant",
            anchor_place_name="Restaurant",
        )
        catalog = project_graph_candidate_catalog(
            _bundle(eligible=[special_rank, cafe_rank, restaurant_rank])
        )
        assert len(catalog.candidates) == 1
        candidate = catalog.candidates[0]
        assert candidate.activity_id == "activity_coffee_tour"
        assert set(candidate.anchor_place_ids) == {"place_cafe_giang", "place_restaurant"}
        assert set(candidate.claim_ids) == {
            "c_special",
            "c_cafe",
            "c_restaurant",
        }
        assert candidate.special_claim_ids == ["c_special"]

    def test_special_experience_activity_no_grouping_without_activity(self) -> None:
        a1 = _ranked(
            "c_se_act1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
            activity_name="Cooking",
        )
        a2 = _ranked(
            "c_se_act2",
            rank=2,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
            activity_name="Cooking",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[a1, a2]))
        assert len(catalog.candidates) == 1
        assert set(catalog.candidates[0].claim_ids) == {"c_se_act1", "c_se_act2"}

    def test_different_activities_produce_separate_candidates(self) -> None:
        a1 = _ranked(
            "c_act1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
        )
        a2 = _ranked(
            "c_act2",
            rank=2,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_coffee",
            object_type="Activity",
            activity_id="activity_coffee",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[a1, a2]))
        assert len(catalog.candidates) == 2


# ---------------------------------------------------------------------------
# Grouping direct Activity anchors (SPECIAL_EXPERIENCE -> Activity -> TARGETS_PLACE)
# ---------------------------------------------------------------------------


class TestDirectAnchorGrouping:
    """Claims for the same Activity merge their direct Place anchors."""

    def test_same_activity_anchors_merged(self) -> None:
        p1 = _ranked(
            "c_p1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_museum_visit",
            object_type="Activity",
            activity_id="activity_museum_visit",
            anchor_place_id="place_museum_a",
            priority=RecommendationPriority.MUST,
            source="https://wiki.org",
        )
        p2 = _ranked(
            "c_p2",
            rank=3,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_museum_visit",
            object_type="Activity",
            activity_id="activity_museum_visit",
            anchor_place_id="place_museum_b",
            priority=RecommendationPriority.OPTIONAL,
            source="https://blog.com",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[p1, p2]))
        assert len(catalog.candidates) == 1
        candidate = catalog.candidates[0]
        assert candidate.place_ids == ["place_museum_a", "place_museum_b"]
        assert set(candidate.claim_ids) == {"c_p1", "c_p2"}
        assert candidate.recommendation is not None
        assert candidate.recommendation.priority is RecommendationPriority.MUST


# ---------------------------------------------------------------------------
# Deterministic deduplication
# ---------------------------------------------------------------------------


class TestDeterministicOutput:
    """The projection is deterministic: same input yields byte-identical output."""

    def test_same_bundle_produces_identical_catalog(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_a",
            object_type="Activity",
            activity_id="activity_a",
        )
        bundle = _bundle(eligible=[ranked])
        result1 = project_graph_candidate_catalog(bundle)
        result2 = project_graph_candidate_catalog(bundle)
        json1 = result1.model_dump_json(by_alias=True)
        json2 = result2.model_dump_json(by_alias=True)
        assert json1 == json2

    def test_identical_claims_merged_deterministically(self) -> None:
        a = _ranked(
            "c_a",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
        )
        b = _ranked(
            "c_b",
            rank=2,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
        )
        catalog1 = project_graph_candidate_catalog(_bundle(eligible=[a, b]))
        catalog2 = project_graph_candidate_catalog(_bundle(eligible=[b, a]))
        assert (
            catalog1.model_dump_json(by_alias=True)
            == catalog2.model_dump_json(by_alias=True)
        )


# ---------------------------------------------------------------------------
# Claim fields preserved
# ---------------------------------------------------------------------------


class TestFieldsPreserved:
    """All required planner fields are faithfully carried through the projection."""

    def test_rank_preserved(self) -> None:
        ranked = _ranked(
            "c1",
            rank=5,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_x",
            object_type="Activity",
            activity_id="activity_x",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates[0].rank == 5

    def test_fit_preserved(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_x",
            object_type="Activity",
            activity_id="activity_x",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates[0].fit.status is CheckStatus.SUPPORTED
        assert catalog.candidates[0].fit.dimensionCount == 2

    def test_trust_preserved(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_x",
            object_type="Activity",
            activity_id="activity_x",
            trust=TrustLevel.VERIFIED,
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates[0].trust is TrustLevel.VERIFIED

    def test_inferred_evidence_remains_explicit(self) -> None:
        ranked = _ranked(
            "c_inferred",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_inferred",
            object_type="Activity",
            activity_id="activity_inferred",
            trust=TrustLevel.INFERRED,
            source="inference:taxonomy",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates[0].trust is TrustLevel.INFERRED
        assert catalog.candidates[0].source_refs == ["inference:taxonomy"]

    def test_recommendation_preserved(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_x",
            object_type="Activity",
            activity_id="activity_x",
            priority=RecommendationPriority.RECOMMENDED,
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert catalog.candidates[0].recommendation is not None
        assert catalog.candidates[0].recommendation.priority is RecommendationPriority.RECOMMENDED

    def test_source_refs_collected(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_x",
            object_type="Activity",
            activity_id="activity_x",
            source="https://wiki.org",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        assert "https://wiki.org" in catalog.candidates[0].source_refs


# ---------------------------------------------------------------------------
# Empty catalog
# ---------------------------------------------------------------------------


class TestEmptyCatalog:
    """Empty eligible list yields an empty catalog."""

    def test_empty_bundle_returns_empty_catalog(self) -> None:
        catalog = project_graph_candidate_catalog(_bundle(eligible=[]))
        assert catalog.candidates == []


# ---------------------------------------------------------------------------
# Candidate catalog model is well-formed
# ---------------------------------------------------------------------------


class TestCatalogModel:
    """The GraphCandidateCatalog model validates correctly."""

    def test_catalog_with_single_candidate_serializes(self) -> None:
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_a",
            object_type="Activity",
            object_name="Activity A",
            activity_id="activity_a",
            priority=RecommendationPriority.MUST,
            source="https://example.com",
        )
        catalog = project_graph_candidate_catalog(_bundle(eligible=[ranked]))
        serialized = catalog.model_dump(mode="json", by_alias=True)
        assert serialized["candidates"][0]["claimIds"] == ["c1"]
        assert serialized["candidates"][0]["placeIds"] == []
        assert serialized["candidates"][0]["rank"] == 1

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(Exception):
            GraphCandidateCatalog.model_validate(
                {"candidates": [{"extraField": "invalid"}]}
            )


# ---------------------------------------------------------------------------
# Internal helpers are unit-testable
# ---------------------------------------------------------------------------


class TestClaimShapeHelper:
    """``_claim_shape`` classifies claim paths correctly."""

    def test_special_experience_place_is_rejected_by_v7(self) -> None:
        from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
            _claim_shape,
        )
        claim = _claim(
            "c1",
            predicate="SPECIAL_EXPERIENCE",
            subject_id="area_hanoi",
            object_id="place_cafe",
            object_type="Cafe",
        )
        assert _claim_shape(claim) is None

    def test_special_experience_activity(self) -> None:
        from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
            _claim_shape,
        )
        claim = _claim(
            "c2",
            predicate="SPECIAL_EXPERIENCE",
            subject_id="area_hanoi",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
            activity_name="Cooking Class",
        )
        assert _claim_shape(claim) == "special_experience_activity"

    def test_offers_activity(self) -> None:
        from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
            _claim_shape,
        )
        claim = _claim(
            "c3",
            predicate="OFFERS_ACTIVITY",
            subject_id="place_cafe",
            object_id="activity_tour",
            object_type="Activity",
            activity_id="activity_tour",
            anchor_place_id="place_cafe",
        )
        assert _claim_shape(claim) == "place_offers_activity"


class TestSelectableHelper:
    """``_is_selectable`` filters correctly."""

    def test_supported_is_selectable(self) -> None:
        from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
            _is_selectable,
        )
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_x",
            object_type="Activity",
            activity_id="activity_x",
        )
        assert _is_selectable(ranked) is True

    def test_conflicted_is_not_selectable(self) -> None:
        from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
            _is_selectable,
        )
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="place_x",
            object_type="TravelPlace",
            supported=False,
            has_hard_conflict=True,
        )
        assert _is_selectable(ranked) is False

    def test_unsupported_predicate_is_not_selectable(self) -> None:
        from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
            _is_selectable,
        )
        ranked = _ranked(
            "c1",
            rank=1,
            predicate="PART_OF",
            object_id="area_x",
            object_type="Area",
        )
        assert _is_selectable(ranked) is False


# ---------------------------------------------------------------------------
# Multiple shapes coexist
# ---------------------------------------------------------------------------


class TestMultipleShapes:
    """A bundle with mixed shapes produces separate candidates."""

    def test_mixed_shapes_only_special_seeded_groups_are_included(self) -> None:
        direct_anchor = _ranked(
            "c_anchor",
            rank=1,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_walk",
            object_type="Activity",
            activity_id="activity_walk",
            anchor_place_id="place_lake",
        )
        activity_se = _ranked(
            "c_activity",
            rank=2,
            predicate="SPECIAL_EXPERIENCE",
            object_id="activity_cooking",
            object_type="Activity",
            activity_id="activity_cooking",
        )
        offers = _ranked(
            "c_offers",
            rank=3,
            predicate="OFFERS_ACTIVITY",
            subject_id="place_cafe",
            object_id="activity_tour",
            object_type="Activity",
            activity_id="activity_tour",
            anchor_place_id="place_cafe",
        )
        catalog = project_graph_candidate_catalog(
            _bundle(eligible=[direct_anchor, activity_se, offers])
        )
        assert len(catalog.candidates) == 2
