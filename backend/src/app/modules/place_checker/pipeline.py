from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter

from app.modules.place_checker.aggregate_analysis import TripAggregateAnalysisService
from app.modules.place_checker.contract import AdmResolutionStatus, PlaceCheckerInput
from app.modules.place_checker.evaluation import PlaceEvaluationService
from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.evidence import EvidenceEnrichmentService
from app.modules.place_checker.item_resolution import InputItemResolutionService
from app.modules.place_checker.output import PlaceCheckerOutputAssembler
from app.modules.place_checker.output_contract import (
    PlaceCheckerExecutionMetadata,
    PlaceCheckerResult,
    ToolCallSummary,
)
from app.modules.place_checker.ports import PlaceCheckerMetricsSink
from app.modules.place_checker.resolution import EntityResolutionService
from app.modules.place_checker.retrieval import TargetedRetrievalService
from app.modules.place_checker.retrieval_projection import RetrievalCandidateProjector
from app.modules.place_checker.scoring import CandidateScoringService
from app.modules.place_checker.service import TripContextBuilder


class PlaceCheckerPipeline:
    def __init__(
        self,
        *,
        context_builder: TripContextBuilder,
        entity_resolution: EntityResolutionService,
        evidence_enrichment: EvidenceEnrichmentService,
        item_resolution: InputItemResolutionService,
        evaluation: PlaceEvaluationService | None = None,
        aggregate_analysis: TripAggregateAnalysisService | None = None,
        targeted_retrieval: TargetedRetrievalService | None = None,
        scoring: CandidateScoringService | None = None,
        metrics: PlaceCheckerMetricsSink | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.entity_resolution = entity_resolution
        self.evidence_enrichment = evidence_enrichment
        self.item_resolution = item_resolution
        self.evaluation = evaluation or PlaceEvaluationService()
        self.aggregate_analysis = aggregate_analysis or TripAggregateAnalysisService()
        self.targeted_retrieval = targeted_retrieval
        self.scoring = scoring or CandidateScoringService()
        self.metrics = metrics
        self.output = PlaceCheckerOutputAssembler()
        self.retrieval_projection = RetrievalCandidateProjector()

    async def check(
        self,
        payload: PlaceCheckerInput,
        *,
        request_id: str,
        correlation_id: str | None = None,
    ) -> PlaceCheckerResult:
        started = perf_counter()
        phase: dict[str, int] = {}
        correlation_id = correlation_id or request_id

        context_started = perf_counter()
        context = await self.context_builder.build(payload)
        phase["trip_context"] = self._elapsed(context_started)

        resolution_started = perf_counter()
        identities = await self.entity_resolution.resolve_all(payload.places, context)
        phase["identity_resolution"] = self._elapsed(resolution_started)

        enrichment_started = perf_counter()
        enriched = await self.evidence_enrichment.merge_and_enrich(
            identities,
            payload.url_notes,
        )
        items = await self.item_resolution.resolve_all(
            payload.input_items,
            context,
            enriched.places,
        )
        phase["evidence_and_items"] = self._elapsed(enrichment_started)

        evaluation_started = perf_counter()
        evaluated = self.evaluation.evaluate_all(enriched.places, context)
        analysis = self.aggregate_analysis.analyze(evaluated, items, context)
        phase["evaluation_and_analysis"] = self._elapsed(evaluation_started)

        retrieval = None
        ranking = None
        verification_by_id = {}
        ranking_by_id = {}
        if (
            self.targeted_retrieval is not None
            and context.destination.status == AdmResolutionStatus.resolved
        ):
            retrieval_started = perf_counter()
            retrieval = await self.targeted_retrieval.retrieve(
                analysis.gaps,
                context,
                items,
                anchor_place_ids=[
                    place.place_id
                    for place in enriched.places
                    if place.place_id
                ],
            )
            ranking = self.scoring.rank(retrieval, context, evaluated)
            optional_places, verification_by_id, ranking_by_id = (
                self.retrieval_projection.to_enriched_places(ranking.ranked, context)
            )
            optional_evaluations = self.evaluation.evaluate_all(optional_places, context)
            evaluated = self._merge_evaluations(evaluated, optional_evaluations)
            analysis = self.aggregate_analysis.analyze(evaluated, items, context)
            phase["retrieval_and_ranking"] = self._elapsed(retrieval_started)

        attempts = [
            attempt
            for gap in (retrieval.gaps if retrieval else [])
            for attempt in gap.attempts
        ]
        metadata = PlaceCheckerExecutionMetadata(
            request_id=request_id,
            correlation_id=correlation_id,
            generated_at=datetime.now(UTC),
            duration_ms=self._elapsed(started),
            phase_duration_ms=phase,
            tool_calls=ToolCallSummary(
                adm_resolver=1,
                search_places_named=len(payload.places),
                search_places_requirement=len(payload.input_items),
                retrieval_search=len(attempts),
                external_search=sum(
                    attempt.source_kind.value == "external" for attempt in attempts
                ),
                metadata_repository=int(bool(payload.places)),
            ),
            partial=bool(
                payload.validation_issues
                or identities.warnings
                or items.warnings
                or enriched.warnings
                or (retrieval and retrieval.warnings)
            ),
        )
        result = self.output.assemble(
            context=context,
            places=evaluated,
            items=items,
            analysis=analysis,
            metadata=metadata,
            validation_issues=payload.validation_issues,
            retrieval=retrieval,
            ranking=ranking,
            verification_by_place_id=verification_by_id,
            ranking_by_place_id=ranking_by_id,
            extra_warnings=[*identities.warnings, *enriched.warnings],
        )
        await self._record_metrics(result)
        return result

    @staticmethod
    def _merge_evaluations(
        base: PlaceEvaluationBatch,
        optional: PlaceEvaluationBatch,
    ) -> PlaceEvaluationBatch:
        seen = {place.place.place_id for place in base.places if place.place.place_id}
        appended = [
            place
            for place in optional.places
            if place.place.place_id not in seen
        ]
        places = [*base.places, *appended]
        return PlaceEvaluationBatch(
            places=places,
            planner_eligible_place_ids=[
                place.place.place_id
                for place in places
                if place.planner_eligible and place.place.place_id
            ],
            warnings=list(dict.fromkeys([*base.warnings, *optional.warnings])),
        )

    async def _record_metrics(self, result: PlaceCheckerResult) -> None:
        if self.metrics is None:
            return
        tags = {
            "status": result.status.value,
            "schema_version": result.metadata.schema_version,
        }
        values = {
            "place_checker.duration_ms": result.metadata.duration_ms,
            "place_checker.checked_places": len(result.checked_places),
            "place_checker.planner_eligible": len(result.planner_eligible_place_ids),
            "place_checker.open_gaps": result.aggregate_analysis.gaps.open_count,
            "place_checker.unresolved_entities": len(result.unresolved_entities),
            "place_checker.external_search_calls": (
                result.metadata.tool_calls.external_search
            ),
            "place_checker.unknown_cost_ratio": self._unknown_cost_ratio(result),
        }
        for metric, value in values.items():
            try:
                await self.metrics.record(metric, float(value), tags)
            except Exception:
                break

    @staticmethod
    def _unknown_cost_ratio(result: PlaceCheckerResult) -> float:
        total = result.aggregate_analysis.budget.total
        if total.place_count == 0:
            return 0.0
        return total.unknown_amount_count / total.place_count

    @staticmethod
    def _elapsed(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))
