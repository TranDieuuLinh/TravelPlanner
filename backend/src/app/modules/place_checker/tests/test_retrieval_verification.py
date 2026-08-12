import asyncio

from app.modules.place_checker.adapters import (
    InMemoryPromotionOutbox,
    SearchPlacesGapSource,
)
from app.modules.place_checker.analysis_contract import AnalysisGap, GapAnalysis
from app.modules.place_checker.enums import (
    CostTier,
    GapType,
    IssueSeverity,
    PromotionEventStatus,
    RetrievalSourceKind,
    VerificationStatus,
)
from app.modules.place_checker.errors import CandidateSourceTimeout
from app.modules.place_checker.promotion import PromotionWorker
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.retrieval_contract import (
    RetrievalEvidence,
    TargetedRetrievalQuery,
)
from app.modules.place_checker.tests.analysis_fixtures import analysis_context
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places import (
    PlaceSearchMatch,
    PlaceSearchResult,
)


class FakeSource:
    def __init__(
        self,
        name: str,
        kind: RetrievalSourceKind,
        evidence: list[RetrievalEvidence] | None = None,
        *,
        timeout: bool = False,
    ) -> None:
        self.provider_name = name
        self.source_kind = kind
        self.evidence = evidence or []
        self.timeout = timeout
        self.calls = 0

    async def search(self, query):
        self.calls += 1
        if self.timeout:
            raise CandidateSourceTimeout()
        return self.evidence


class FakePromotionCatalog:
    def __init__(self, *, duplicate_id: str | None = None, fail: bool = False) -> None:
        self.duplicate_id = duplicate_id
        self.fail = fail
        self.promoted = 0

    async def find_duplicate(self, candidate):
        return self.duplicate_id

    async def promote(self, candidate):
        if self.fail:
            raise RuntimeError("catalog unavailable")
        self.promoted += 1
        return f"kg:{candidate.candidate_key}"


class FakeSearchTool:
    def __init__(self, result: PlaceSearchResult) -> None:
        self.result = result
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        return self.result


class FakeMetadataRepository:
    async def get_many(self, place_ids):
        return {
            "kg:pho": PlaceMetadata(
                place_id="kg:pho",
                cost_tier=CostTier.low,
                typical_duration_minutes=60,
            )
        }


def gap(gap_type: GapType = GapType.food_coverage) -> GapAnalysis:
    return GapAnalysis(
        gaps=[
            AnalysisGap(
                gap_id=f"gap:{gap_type.value}",
                gap_type=gap_type,
                severity=IssueSeverity.high,
                trigger="missing coverage",
                suggested_action="search",
            )
        ],
        open_count=1,
    )


def evidence(
    name: str = "Pho Bat Dan",
    *,
    entity_id: str | None = None,
    category: str = "food",
    latitude: float = 21.034,
) -> RetrievalEvidence:
    return RetrievalEvidence(
        provider="placeholder",
        source_kind=RetrievalSourceKind.external,
        provider_id=f"provider:{name}:{latitude}",
        entity_id=entity_id,
        name=name,
        adm_id="adm1_vn_ha_noi",
        category=category,
        coordinates=Coordinates(latitude=latitude, longitude=105.847),
        confidence=0.9,
    )


def test_kg_sufficient_short_circuits_external_sources() -> None:
    kg = FakeSource(
        "knowledge_graph",
        RetrievalSourceKind.knowledge_graph,
        [evidence(entity_id="kg:pho")],
    )
    external = FakeSource("external_a", RetrievalSourceKind.external, [evidence()])
    service = TargetedRetrievalService(
        kg,
        external_sources=[external],
        verified_target_per_gap=1,
    )

    result = asyncio.run(service.retrieve(gap(), analysis_context()))

    candidate = result.gaps[0].candidates[0]
    assert candidate.verification_status == VerificationStatus.verified_kg
    assert candidate.planner_eligible is True
    assert external.calls == 0


def test_one_external_source_is_provisional_and_not_eligible() -> None:
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=[
            FakeSource("external_a", RetrievalSourceKind.external, [evidence()])
        ],
    )

    result = asyncio.run(service.retrieve(gap(), analysis_context()))
    candidate = result.gaps[0].candidates[0]

    assert candidate.verification_status == VerificationStatus.provisional
    assert candidate.planner_eligible is False
    assert result.promotion_event_ids == []


def test_two_independent_sources_verify_and_queue_once() -> None:
    outbox = InMemoryPromotionOutbox()
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=[
            FakeSource("external_a", RetrievalSourceKind.external, [evidence()]),
            FakeSource("external_b", RetrievalSourceKind.external, [evidence()]),
        ],
        promotion_outbox=outbox,
    )

    first = asyncio.run(service.retrieve(gap(), analysis_context()))
    second = asyncio.run(service.retrieve(gap(), analysis_context()))

    candidate = first.gaps[0].candidates[0]
    assert candidate.verification_status == VerificationStatus.verified_external
    assert candidate.planner_eligible is True
    assert first.promotion_event_ids == second.promotion_event_ids
    assert len(outbox.events) == 1


def test_provider_conflict_requires_review() -> None:
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=[
            FakeSource("external_a", RetrievalSourceKind.external, [evidence()]),
            FakeSource(
                "external_b",
                RetrievalSourceKind.external,
                [evidence(category="nightlife", latitude=21.20)],
            ),
        ],
    )

    result = asyncio.run(service.retrieve(gap(), analysis_context()))

    assert all(
        item.verification_status == VerificationStatus.needs_review
        for item in result.gaps[0].candidates
    )
    assert not any(item.planner_eligible for item in result.gaps[0].candidates)


def test_external_timeout_returns_partial_result() -> None:
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=[
            FakeSource(
                "external_a",
                RetrievalSourceKind.external,
                timeout=True,
            )
        ],
    )

    result = asyncio.run(service.retrieve(gap(), analysis_context()))

    assert result.gaps[0].candidates == []
    assert result.gaps[0].attempts[-1].outcome == "timeout"
    assert result.gaps[0].warnings


def test_promotion_worker_detects_duplicate_and_is_idempotent() -> None:
    outbox = InMemoryPromotionOutbox()
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=[
            FakeSource("external_a", RetrievalSourceKind.external, [evidence()]),
            FakeSource("external_b", RetrievalSourceKind.external, [evidence()]),
        ],
        promotion_outbox=outbox,
    )
    asyncio.run(service.retrieve(gap(), analysis_context()))
    worker = PromotionWorker(outbox, FakePromotionCatalog(duplicate_id="kg:existing"))

    first = asyncio.run(worker.run_once())
    second = asyncio.run(worker.run_once())

    assert first[0].duplicate is True
    assert first[0].entity_id == "kg:existing"
    assert second == []


def test_promotion_failure_does_not_raise() -> None:
    outbox = InMemoryPromotionOutbox()
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=[
            FakeSource("external_a", RetrievalSourceKind.external, [evidence()]),
            FakeSource("external_b", RetrievalSourceKind.external, [evidence()]),
        ],
        promotion_outbox=outbox,
    )
    result = asyncio.run(service.retrieve(gap(), analysis_context()))

    work = asyncio.run(PromotionWorker(outbox, FakePromotionCatalog(fail=True)).run_once())

    assert result.gaps[0].candidates[0].planner_eligible is True
    assert work[0].status == PromotionEventStatus.failed


def test_search_places_adapter_scopes_requirement_to_adm() -> None:
    tool = FakeSearchTool(
        PlaceSearchResult(
            status="resolved",
            query="food tại Hà Nội",
            normalized_query="food tai ha noi",
            search_mode="requirement",
            selected=PlaceSearchMatch(
                place_id="kg:pho",
                provider="knowledge_graph",
                name="Pho Bat Dan",
                coordinates=Coordinates(latitude=21.034, longitude=105.847),
                score=0.9,
                relationship_score=1.0,
            ),
            top_matches=[
                PlaceSearchMatch(
                    place_id="kg:pho",
                    provider="knowledge_graph",
                    name="Pho Bat Dan",
                    coordinates=Coordinates(latitude=21.034, longitude=105.847),
                    score=0.9,
                    relationship_score=1.0,
                )
            ],
            resolution_reason="requirement_match",
        )
    )
    source = SearchPlacesGapSource(
        tool,
        provider_name="knowledge_graph",
        source_kind=RetrievalSourceKind.knowledge_graph,
    )
    service = TargetedRetrievalService(
        source,
        metadata_repository=FakeMetadataRepository(),
        verified_target_per_gap=1,
    )

    result = asyncio.run(
        service.retrieve(
            gap(),
            analysis_context(),
            anchor_place_ids=["kg:anchor"],
        )
    )

    request = tool.requests[0]
    assert request.search_mode == "requirement"
    assert request.input_adm.adm_id == "adm1_vn_ha_noi"
    assert request.allow_external_fallback is False
    assert request.anchor_place_id == "kg:anchor"
    assert result.gaps[0].candidates[0].place_id == "kg:pho"
    assert result.gaps[0].candidates[0].relationship_score == 1.0
    assert result.gaps[0].candidates[0].metadata.cost_tier == CostTier.low
    assert result.gaps[0].candidates[0].metadata.typical_duration_minutes == 60


def test_relation_candidates_are_selected_before_keyword_fallbacks() -> None:
    fallback = PlaceSearchMatch(
        place_id="kg:keyword",
        provider="knowledge_graph",
        name="Keyword Place",
        coordinates=Coordinates(latitude=21.034, longitude=105.847),
        score=0.95,
        relationship_score=0,
    )
    related = PlaceSearchMatch(
        place_id="kg:related",
        provider="knowledge_graph",
        name="Related Place",
        coordinates=Coordinates(latitude=21.035, longitude=105.848),
        score=0.70,
        relationship_score=0.85,
    )
    tool = FakeSearchTool(
        PlaceSearchResult(
            status="resolved",
            query="culture",
            normalized_query="culture",
            search_mode="requirement",
            top_matches=[fallback, related],
            resolution_reason="requirement_match",
        )
    )
    source = SearchPlacesGapSource(
        tool,
        provider_name="knowledge_graph",
        source_kind=RetrievalSourceKind.knowledge_graph,
    )
    query = TargetedRetrievalQuery(
        gap_id="pool:culture_alternatives",
        gap_type=GapType.experience_coverage,
        severity=IssueSeverity.low,
        query_text="culture",
        adm_id="adm1_vn_ha_noi",
        adm_name="Hà Nội",
        country_code="VN",
        budget_level="low",
        anchor_place_ids=["kg:anchor"],
        limit=1,
    )

    result = asyncio.run(source.search(query))

    assert [item.entity_id for item in result] == ["kg:related"]
    assert "retrieval:relation" in result[0].tags
    assert tool.requests[0].top_k == 3


def test_external_call_budget_uses_at_most_two_sources() -> None:
    sources = [
        FakeSource(f"external_{index}", RetrievalSourceKind.external)
        for index in range(3)
    ]
    service = TargetedRetrievalService(
        FakeSource("kg", RetrievalSourceKind.knowledge_graph),
        external_sources=sources,
    )

    asyncio.run(service.retrieve(gap(), analysis_context()))

    assert [source.calls for source in sources] == [1, 1, 0]
