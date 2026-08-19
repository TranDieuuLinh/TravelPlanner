import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.place_checker.adapters import InMemoryPlaceCheckerMetrics
from app.modules.place_checker.aggregate_analysis import TripAggregateAnalysisService
from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    PlaceCheckerInput,
)
from app.modules.place_checker.enums import (
    CostTier,
    OperationalStatus,
    RetrievalSourceKind,
    SourceTier,
    VerificationStatus,
)
from app.modules.place_checker.evaluation import PlaceEvaluationService
from app.modules.place_checker.evidence import EvidenceEnrichmentService
from app.modules.place_checker.graph import build_place_checker_pipeline_graph
from app.modules.place_checker.input_projection import ExplorerInputProjector
from app.modules.place_checker.item_resolution import InputItemResolutionService
from app.modules.place_checker.planning_output import PlaceCheckerPlanningProjector
from app.modules.place_checker.output_contract import PlaceCheckerResult
from app.modules.place_checker.pipeline import PlaceCheckerPipeline
from app.modules.place_checker.resolution import EntityResolutionService
from app.modules.place_checker.resolution_contract import PlaceMetadata
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.retrieval_contract import RetrievalEvidence
from app.modules.place_checker.scoring import CandidateScoringService
from app.modules.place_checker.service import TripContextBuilder
from app.modules.explorer.public import ExplorerOutput
from app.orchestration.nodes import RootNodes
from app.shared.contracts.place import Coordinates, PlaceCandidate
from app.shared.contracts.trip import TripIntent
from app.shared.tools.search_places import PlaceProviderCandidate, SearchPlacesTool
from app.shared.tools.search_places.adapters import InMemoryPlaceSearch


NOW = datetime(2026, 8, 11, tzinfo=UTC)
ADM_ID = "adm1_vn_ha_noi"


class FakeAdmResolver:
    async def resolve(self, input_name: str) -> AdmResolution:
        return AdmResolution(
            input_name=input_name,
            status=AdmResolutionStatus.resolved,
            adm_id=ADM_ID,
            canonical_name="Hà Nội",
            country_code="VN",
            region_key="vn,ha_noi",
        )


class FakeMetadataRepository:
    def __init__(self) -> None:
        self.data = {
            "kg:mausoleum": metadata(
                "kg:mausoleum",
                category="landmark",
                cost_tier=CostTier.free,
                latitude=21.0368,
            ),
            "kg:pho": metadata(
                "kg:pho",
                category="restaurant",
                cost_tier=CostTier.low,
                latitude=21.0338,
            ),
            "kg:garden": metadata(
                "kg:garden",
                category="garden",
                cost_tier=CostTier.low,
                latitude=21.0288,
            ),
        }

    async def get_many(self, place_ids):
        return {place_id: self.data[place_id] for place_id in place_ids if place_id in self.data}


class FakeGapSource:
    provider_name = "knowledge_graph"
    source_kind = RetrievalSourceKind.knowledge_graph

    async def search(self, query):
        return [
            RetrievalEvidence(
                provider=self.provider_name,
                source_kind=self.source_kind,
                entity_id="kg:garden",
                name="Hanoi Botanical Garden",
                adm_id=ADM_ID,
                category="garden",
                coordinates=Coordinates(latitude=21.0288, longitude=105.8340),
                tags=["nature", "garden"],
                confidence=0.92,
            )
        ]


def metadata(
    place_id: str,
    *,
    category: str,
    cost_tier: CostTier,
    latitude: float,
) -> PlaceMetadata:
    free = cost_tier == CostTier.free
    return PlaceMetadata(
        place_id=place_id,
        coordinates=Coordinates(latitude=latitude, longitude=105.8340),
        category=category,
        tags=[category],
        minimum_duration_minutes=45,
        typical_duration_minutes=60,
        maximum_duration_minutes=90,
        cost_tier=cost_tier,
        cost_currency="VND",
        minimum_cost=0 if free else 30000,
        typical_cost=0 if free else 50000,
        maximum_cost=0 if free else 80000,
        opening_hours=["09:00-17:00"],
        operational_status=OperationalStatus.active,
        reservation_required=False,
        children_suitable=True,
        infants_suitable=True,
        source="knowledge_graph",
        fetched_at=NOW,
    )


def payload() -> PlaceCheckerInput:
    return PlaceCheckerInput.model_validate(
        {
            "input_ADM": "Hanoi",
            "places": [
                {
                    "name": "Ho Chi Minh Mausoleum",
                    "confidence": 0.98,
                    "source_places": [
                        {
                            "origin": "input",
                            "evidence_type": "raw_prompt",
                            "evidence": "Visit Ho Chi Minh Mausoleum",
                        }
                    ],
                }
            ],
            "input_items": [
                {
                    "name": "pho",
                    "item_type": "food",
                    "action": "eat",
                    "evidence": "eat pho",
                    "confidence": 0.97,
                }
            ],
            "url_notes": None,
            "days": 4,
            "budget": {
                "level": "low",
                "target_amount": None,
                "currency": "VND",
                "source": "raw_prompt",
            },
            "people": {"adults": 1, "children": 0, "infants": 0},
            "short_preferences": ["nature"],
            "short_avoids": ["nightlife"],
        }
    )


def pipeline(*, metrics=None) -> PlaceCheckerPipeline:
    catalog = [
        PlaceProviderCandidate(
            provider="knowledge_graph",
            entity_id="kg:mausoleum",
            name="Ho Chi Minh Mausoleum",
            adm_ids=[ADM_ID],
            adm_names=["Hà Nội"],
            canonical_type="landmark",
            coordinates=Coordinates(latitude=21.0368, longitude=105.8340),
            data_confidence=0.99,
        ),
        PlaceProviderCandidate(
            provider="knowledge_graph",
            entity_id="kg:pho",
            name="Pho Bat Dan",
            adm_ids=[ADM_ID],
            adm_names=["Hà Nội"],
            canonical_type="restaurant",
            tags=["pho", "food"],
            relationship_score=0.9,
            coordinates=Coordinates(latitude=21.0338, longitude=105.8340),
            data_confidence=0.95,
        ),
    ]
    repository = FakeMetadataRepository()
    search_tool = SearchPlacesTool(
        InMemoryPlaceSearch(catalog, provider_name="knowledge_graph")
    )
    return PlaceCheckerPipeline(
        context_builder=TripContextBuilder(FakeAdmResolver()),
        entity_resolution=EntityResolutionService(search_tool),
        evidence_enrichment=EvidenceEnrichmentService(repository),
        item_resolution=InputItemResolutionService(
            search_tool,
            metadata_repository=repository,
        ),
        evaluation=PlaceEvaluationService(now=NOW),
        aggregate_analysis=TripAggregateAnalysisService(),
        targeted_retrieval=TargetedRetrievalService(
            FakeGapSource(),
            metadata_repository=repository,
            verified_target_per_gap=1,
        ),
        scoring=CandidateScoringService(now=NOW),
        metrics=metrics,
    )


def test_pipeline_builds_rich_output_and_planning_projection() -> None:
    metrics = InMemoryPlaceCheckerMetrics()
    result = asyncio.run(
        pipeline(metrics=metrics).check(
            payload(),
            request_id="request-1",
            correlation_id="correlation-1",
        )
    )
    projection = PlaceCheckerPlanningProjector().project(result)

    assert result.trip_context.destination.canonical_name == "Hà Nội"
    assert "kg:mausoleum" in result.planner_eligible_place_ids
    assert result.resolved_items[0].selected.place_id == "kg:pho"
    assert any(place.place_id == "kg:garden" for place in result.checked_places)
    assert all(place.provenance for place in projection.places)
    assert projection.resolved_items[0].selected.place_id == "kg:pho"
    assert projection.destination_adm_id == ADM_ID
    assert result.metadata.correlation_id == "correlation-1"
    assert metrics.records
    assert result.status.value == "blocked"
    assert any("Planner meal candidate pool is incomplete" in item for item in result.warnings)


def test_pipeline_graph_exposes_result_without_day_or_route_fields() -> None:
    graph = build_place_checker_pipeline_graph(pipeline())

    state = asyncio.run(
        graph.ainvoke({"request_id": "request-2", "payload": payload()})
    )
    dumped = state["result"].model_dump()

    assert "day" not in dumped
    assert "route_order" not in dumped
    assert "travel_leg" not in dumped
    assert {
        "budget_analysis",
        "capacity_analysis",
        "coverage_analysis",
        "geographic_analysis",
        "gap_analysis",
    }.issubset(dumped)
    assert "aggregate_analysis" not in dumped
    assert "internal_evaluation" not in dumped["checked_places"][0]

    with pytest.raises(ValidationError):
        state["result"].__class__.model_validate({**dumped, "day": 1})


def test_pipeline_graph_accepts_raw_camel_case_payload() -> None:
    graph = build_place_checker_pipeline_graph(pipeline())
    raw = payload().model_dump(
        mode="json", by_alias=True, exclude={"validation_issues"}
    )

    state = asyncio.run(
        graph.ainvoke({"request_id": "request-camel", "payload": raw})
    )

    assert state["result"].trip_context.destination.adm_id == ADM_ID


def test_orchestration_blocks_incomplete_candidate_pools_before_planner() -> None:
    raw = payload().model_dump(
        mode="json", by_alias=True, exclude={"validation_issues"}
    )
    explorer_places = [
        {
            key: value
            for key, value in place.items()
            if key not in {"latitude", "longitude", "tags"}
        }
        for place in raw["places"]
    ]
    explorer_output = ExplorerOutput.model_validate(
        {
            "status": "ready",
            "intakeId": "intake-1",
            "input_ADM": raw["inputADM"],
            "places": explorer_places,
            "inputItems": raw["inputItems"],
            "urlNotes": raw["urlNotes"],
            "days": raw["days"],
            "budget": raw["budget"],
            "people": raw["people"],
            "shortPreferences": raw["shortPreferences"],
            "shortAvoids": raw["shortAvoids"],
        }
    )
    nodes = RootNodes(place_checker_pipeline=pipeline())

    update = asyncio.run(
        nodes.run_place_checker(
            {
                "request_id": "request-orchestration",
                "explorer_output": explorer_output,
                "warnings": [],
            }
        )
    )

    assert isinstance(update["place_output"], PlaceCheckerResult)
    assert update["place_output"].status.value == "blocked"
    assert "planner_input" not in update
    assert any("Planner meal candidate pool is incomplete" in item for item in update["warnings"])
    assert update["place_output"].trip_context.destination.adm_id == ADM_ID
    assert update["place_output"].schema_version == "place_checker.v1"


def test_documented_output_sample_matches_runtime_contract() -> None:
    path = Path(__file__).parents[1] / "docs" / "output_place_checker.json"

    result = PlaceCheckerResult.model_validate(json.loads(path.read_text()))

    assert result.checked_places[0].place_id == "kg_ho_chi_minh_mausoleum"
    assert result.metadata.sample_data is True


def test_planning_projection_keeps_provisional_direct_input() -> None:
    result = asyncio.run(
        pipeline().check(payload(), request_id="request-provisional")
    )
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "verification": first.verification.model_copy(
                update={"status": VerificationStatus.provisional}
            )
        }
    )

    projection = PlaceCheckerPlanningProjector().project(result)

    projected = next(place for place in projection.places if place.place_id == first.place_id)
    assert projected.verification_status == VerificationStatus.provisional


def test_planning_projection_rejects_provisional_system_suggestion() -> None:
    result = asyncio.run(
        pipeline().check(payload(), request_id="request-provisional-system")
    )
    first = result.checked_places[0]
    result.checked_places[0] = first.model_copy(
        update={
            "source_tier": SourceTier.system_suggested,
            "verification": first.verification.model_copy(
                update={"status": VerificationStatus.provisional}
            ),
        }
    )

    projection = PlaceCheckerPlanningProjector().project(result)

    assert first.place_id not in {place.place_id for place in projection.places}


def test_legacy_explorer_projection_preserves_intent_and_provenance() -> None:
    projected = ExplorerInputProjector.from_legacy(
        TripIntent(destination="Hanoi", days=2, preferences=["history"]),
        [
            PlaceCandidate(
                name="Ho Chi Minh Mausoleum",
                coordinates=Coordinates(latitude=21.0368, longitude=105.8340),
            )
        ],
    )

    assert projected.input_adm == "Hanoi"
    assert projected.days == 2
    assert projected.places[0].source_places[0].evidence_type == "legacy_candidate"
