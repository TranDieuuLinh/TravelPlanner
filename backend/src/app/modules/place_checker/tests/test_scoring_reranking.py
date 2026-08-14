from datetime import UTC, datetime, timedelta

from app.modules.place_checker.enums import (
    CostTier,
    GapType,
    IssueSeverity,
    OperationalStatus,
    RetrievalSourceKind,
    VerificationStatus,
)
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.modules.place_checker.retrieval_contract import (
    GapRetrievalResult,
    RetrievalBatch,
    RetrievalEvidence,
    RetrievedCandidate,
    TargetedRetrievalQuery,
)
from app.modules.place_checker.scoring import WEIGHTS, CandidateScoringService
from app.modules.place_checker.tests.analysis_fixtures import (
    analysis_context,
    evaluated_place,
    place_batch,
)
from app.shared.contracts.place import Coordinates

NOW = datetime(2026, 8, 11, tzinfo=UTC)


def candidate(
    key: str,
    *,
    category: str = "museum",
    experience_type: str | None = None,
    cost_tier: CostTier = CostTier.low,
    confidence: float = 0.9,
    coordinates: Coordinates | None = None,
    tags: list[str] | None = None,
    status: VerificationStatus = VerificationStatus.verified_kg,
    operational_status: OperationalStatus = OperationalStatus.active,
    fetched_at: datetime = NOW,
    pool_category: str | None = None,
    with_cost: bool = True,
) -> RetrievedCandidate:
    coordinates = coordinates or Coordinates(latitude=21.03, longitude=105.84)
    typical_cost = {
        CostTier.free: 0,
        CostTier.low: 50_000,
        CostTier.medium: 200_000,
        CostTier.high: 500_000,
        CostTier.premium: 800_000,
        CostTier.unknown: None,
    }[cost_tier]
    if not with_cost:
        typical_cost = None
    metadata = PlaceMetadata(
        place_id=key,
        coordinates=coordinates,
        category=category,
        pool_category=pool_category,
        tags=tags or [category],
        typical_duration_minutes=90,
        cost_tier=cost_tier,
        cost_currency="VND" if typical_cost is not None else None,
        typical_cost=typical_cost,
        opening_hours=["09:00-17:00"],
        operational_status=operational_status,
        children_suitable=True,
        infants_suitable=True,
        fetched_at=fetched_at,
    )
    evidence = RetrievalEvidence(
        provider="knowledge_graph",
        source_kind=RetrievalSourceKind.knowledge_graph,
        entity_id=key,
        name=f"Place {key}",
        adm_id="adm1_vn_ha_noi",
        category=category,
        experience_type=experience_type,
        coordinates=coordinates,
        tags=tags or [category],
        confidence=confidence,
        metadata=metadata,
    )
    return RetrievedCandidate(
        candidate_key=key,
        gap_id="gap:diversity",
        gap_type=GapType.diversity,
        gap_severity=IssueSeverity.medium,
        canonical_name=f"Place {key}",
        place_id=key if status == VerificationStatus.verified_kg else None,
        adm_id="adm1_vn_ha_noi",
        category=category,
        pool_category=pool_category,
        experience_type=experience_type,
        coordinates=coordinates,
        tags=tags or [category],
        metadata=metadata,
        verification_status=status,
        planner_eligible=status in {
            VerificationStatus.verified_kg,
            VerificationStatus.verified_external,
        },
        evidence=[evidence],
    )


def retrieval(*candidates: RetrievedCandidate) -> RetrievalBatch:
    query = TargetedRetrievalQuery(
        gap_id="gap:diversity",
        gap_type=GapType.diversity,
        severity=IssueSeverity.medium,
        query_text="diversity tại Hà Nội",
        adm_id="adm1_vn_ha_noi",
        adm_name="Hà Nội",
        country_code="VN",
        budget_level="low",
    )
    return RetrievalBatch(
        gaps=[
            GapRetrievalResult(
                gap_id="gap:diversity",
                query=query,
                candidates=list(candidates),
            )
        ]
    )


def empty_places():
    return place_batch()


def test_component_arithmetic_uses_documented_weights() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("one")),
        analysis_context(),
        empty_places(),
    ).ranked[0]

    expected = sum(
        WEIGHTS[name] * value
        for name, value in result.components.model_dump().items()
    )
    assert result.base_score == round(expected, 6)


def test_penalty_is_bounded() -> None:
    expensive_nightlife = candidate(
        "club",
        category="nightlife",
        cost_tier=CostTier.premium,
        tags=["nightlife"],
        coordinates=Coordinates(latitude=22.0, longitude=106.8),
        fetched_at=NOW - timedelta(days=180),
    )
    context = analysis_context()
    context.avoids.append("nightlife")
    existing = place_batch(evaluated_place("existing", category="nightlife"))

    batch = CandidateScoringService(now=NOW).rank(
        retrieval(expensive_nightlife),
        context,
        existing,
    )
    result = batch.excluded[0]

    assert result.penalty_total <= 0.65
    assert result.final_score >= 0
    assert result.eligible is False
    assert "avoid_conflict" in result.exclusion_reasons
    assert "avoid_conflict" in result.penalties
    assert "geographic_outlier" in result.penalties


def test_retrieved_alcohol_candidate_is_hard_filtered_via_alias() -> None:
    context = analysis_context()
    context.avoids.append("alcohol")

    batch = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("cocktail", tags=["item:Cocktail"])),
        context,
        empty_places(),
    )

    assert batch.ranked == []
    assert batch.excluded[0].exclusion_reasons == ["avoid_conflict"]


def test_keyword_fallback_receives_real_ranking_penalty() -> None:
    fallback = candidate("fallback", tags=["museum", "retrieval:keyword_fallback"])

    result = CandidateScoringService(now=NOW).rank(
        retrieval(fallback),
        analysis_context(),
        empty_places(),
    ).ranked[0]

    assert result.penalties["keyword_fallback"] == 0.08


def test_low_budget_prefers_low_cost_candidate() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(
            candidate("premium", cost_tier=CostTier.premium, confidence=0.98),
            candidate("local", cost_tier=CostTier.low, confidence=0.85),
        ),
        analysis_context(level="low"),
        empty_places(),
    )

    assert result.ranked[0].candidate.candidate_key == "local"
    premium = next(
        item for item in result.ranked if item.candidate.candidate_key == "premium"
    )
    assert "high_cost_mismatch" in premium.penalties


def test_provisional_candidate_is_excluded() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("unverified", status=VerificationStatus.provisional)),
        analysis_context(),
        empty_places(),
    )

    assert result.ranked == []
    assert result.excluded[0].exclusion_reasons == ["identity_not_verified"]
    assert "low_verification" in result.excluded[0].penalties


def test_candidate_without_usable_cost_is_excluded() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("unknown-price", with_cost=False)),
        analysis_context(),
        empty_places(),
    )

    assert result.ranked == []
    assert result.excluded[0].exclusion_reasons == ["missing_cost"]


def test_permanently_closed_candidate_is_filtered_before_ranking() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(
            candidate(
                "closed",
                operational_status=OperationalStatus.permanently_closed,
            )
        ),
        analysis_context(),
        empty_places(),
    )

    assert result.ranked == []
    assert "permanently_closed" in result.excluded[0].exclusion_reasons


def test_diversity_reranking_moves_different_category_forward() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(
            candidate("museum_a", category="museum", confidence=0.99),
            candidate("museum_b", category="museum", confidence=0.97),
            candidate("garden", category="garden", confidence=0.90),
        ),
        analysis_context(),
        empty_places(),
    )

    keys = [item.candidate.candidate_key for item in result.ranked]
    first_two_categories = {
        result.ranked[0].candidate.category,
        result.ranked[1].candidate.category,
    }
    assert first_two_categories == {"museum", "garden"}
    assert keys[2] in {"museum_a", "museum_b"}
    assert "repeated_category" in result.ranked[2].rerank_reasons


def test_same_geographic_cluster_is_kept_without_a_penalty() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(
            candidate("near_a", coordinates=Coordinates(latitude=21.03, longitude=105.84)),
            candidate("near_b", coordinates=Coordinates(latitude=21.031, longitude=105.841)),
        ),
        analysis_context(),
        empty_places(),
    )

    assert "same_geographic_cluster" in result.ranked[1].rerank_reasons
    assert round(
        result.ranked[1].final_score - result.ranked[1].rerank_score,
        6,
    ) == 0.08


def test_distant_geographic_cluster_is_penalized() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(
            candidate("a", coordinates=Coordinates(latitude=21.03, longitude=105.84)),
            candidate("b", coordinates=Coordinates(latitude=21.13, longitude=105.84)),
        ),
        analysis_context(),
        empty_places(),
    )

    assert "distant_geographic_cluster" in result.ranked[1].rerank_reasons


def test_candidate_far_from_existing_anchor_is_kept_with_penalty() -> None:
    existing = place_batch(
        evaluated_place(
            "anchor",
            coordinates=Coordinates(latitude=21.03, longitude=105.84),
        )
    )
    far = candidate(
        "far",
        coordinates=Coordinates(latitude=21.35, longitude=106.20),
    )

    result = CandidateScoringService(now=NOW).rank(
        retrieval(far),
        analysis_context(),
        existing,
    )

    assert len(result.ranked) == 1
    assert "geographic_outlier" in result.ranked[0].penalties


def test_tie_break_is_deterministic() -> None:
    service = CandidateScoringService(now=NOW)
    batch = retrieval(candidate("b"), candidate("a"))

    first = service.rank(batch, analysis_context(), empty_places())
    second = service.rank(batch, analysis_context(), empty_places())

    assert [item.candidate.candidate_key for item in first.ranked] == [
        item.candidate.candidate_key for item in second.ranked
    ]
    assert first.ranked[0].candidate.candidate_key == "a"


def test_reserve_limit_caps_each_gap() -> None:
    result = CandidateScoringService(now=NOW).rank(
        retrieval(candidate("a"), candidate("b"), candidate("c")),
        analysis_context(),
        empty_places(),
        reserve_limit_per_gap=2,
    )

    assert len(result.ranked) == 2


def test_default_reserve_grows_with_trip_days() -> None:
    context = analysis_context().model_copy(update={"days": 4})
    result = CandidateScoringService(now=NOW).rank(
        retrieval(*(candidate(str(index)) for index in range(8))),
        context,
        empty_places(),
    )

    assert result.reserve_limit_per_gap == 60
    assert result.pool_target == 69
    assert len(result.ranked) == 8


def test_global_ranking_can_exceed_per_gap_limit() -> None:
    first_gap = retrieval(*(candidate(f"first-{index}") for index in range(6)))
    second_gap = retrieval(*(candidate(f"second-{index}") for index in range(6)))
    second_gap = second_gap.model_copy(
        update={
            "gaps": [
                second_gap.gaps[0].model_copy(
                    update={
                        "gap_id": "gap:second",
                        "candidates": [
                            item.model_copy(update={"gap_id": "gap:second"})
                            for item in second_gap.gaps[0].candidates
                        ],
                    }
                )
            ]
        }
    )
    batch = first_gap.model_copy(update={"gaps": [*first_gap.gaps, *second_gap.gaps]})

    result = CandidateScoringService(now=NOW).rank(
        batch,
        analysis_context().model_copy(update={"days": 5}),
        empty_places(),
    )

    assert len(result.ranked) == 12
    assert result.ranked[-1].rank == 12


def test_pool_category_balancing_keeps_discovery_groups_in_pool() -> None:
    groups = [
        "food", "drink", "culture", "nature", "shopping", "nightlife",
        "workshop", "performance", "outdoor", "family",
        "special_experience", "local_activity",
    ]
    result = CandidateScoringService().rank(
        retrieval(
            *[
                candidate(
                    f"{index}-{group}",
                    pool_category=group,
                    category="travel_place",
                )
                for group in groups
                for index in range(2)
            ]
        ),
        analysis_context().model_copy(update={"days": 1}),
        empty_places(),
        reserve_limit_per_gap=20,
        max_total_candidates=12,
    )

    selected_groups = {
        item.candidate.pool_category
        for item in result.ranked
    }
    assert len(result.ranked) == 12
    assert selected_groups == set(groups)
