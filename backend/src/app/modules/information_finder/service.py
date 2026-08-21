from dataclasses import dataclass
from datetime import datetime, timezone
import logging

from app.modules.information_finder.contract import (
    AnswerMetadata,
    AnswerClaim,
    InformationFinderOutput,
    RetrievedSource,
)
from app.modules.information_finder.errors import (
    AnswerProviderInvalidOutput,
    EmbeddingProviderError,
    SearchQueryPlanningError,
)
from app.modules.information_finder.entity_linking import (
    EntityResolver,
    link_verified_entities,
    materialize_entity_spans,
)
from app.modules.information_finder.answering import (
    block_source_ids,
    build_answer_metadata,
    invalid_answer_source_ids,
    suggestions_from_blocks,
    validate_and_render_answer,
)
from app.modules.information_finder.freshness import FreshnessPolicy
from app.modules.information_finder.ports import (
    AnswerGenerator,
    EmbeddingProvider,
    SearchProvider,
    SearchProviderError,
    SearchQueryPlanner,
    SourceChunker,
    SourceRepository,
)
from app.modules.information_finder.ranking import rank_sources
from app.modules.information_finder.source_processing import SourceProcessingMixin
from app.modules.information_finder.utils import normalize_query
from app.modules.information_finder.tools.budget_ranges import BudgetRangeResult, BudgetRangeTool


@dataclass(frozen=True)
class InformationFinderOptions:
    retrieval_limit: int = 10
    answer_source_limit: int = 5
    provider_relevance_threshold: float = 0.5
    minimum_content_chars: int = 80
    blocked_domains: tuple[str, ...] = ()
    chunk_tokens: int = 300
    chunk_overlap: int = 50
    topic_overlap_threshold: float = 0.75
    max_tavily_attempts: int = 3
    answer_fallback_enabled: bool = True


logger = logging.getLogger(__name__)


class InformationFinderService(SourceProcessingMixin):
    def __init__(
        self,
        *,
        repository: SourceRepository,
        embeddings: EmbeddingProvider,
        answers: AnswerGenerator,
        fallback_answers: AnswerGenerator | None = None,
        chunker: SourceChunker | None = None,
        search_provider: SearchProvider | None = None,
        search_query_planner: SearchQueryPlanner | None = None,
        entity_resolver: EntityResolver | None = None,
        freshness: FreshnessPolicy | None = None,
        options: InformationFinderOptions | None = None,
        budget_ranges: BudgetRangeTool | None = None,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.answers = answers
        self.fallback_answers = fallback_answers
        self.chunker = chunker
        self.search_provider = search_provider
        self.search_query_planner = search_query_planner
        self.entity_resolver = entity_resolver
        self.freshness = freshness or FreshnessPolicy()
        self.options = options or InformationFinderOptions()
        self.budget_ranges = budget_ranges

    async def suggest_budget_range(
        self, region: str, *, category: str | None = None, currency: str = "VND"
    ) -> BudgetRangeResult | None:
        if self.budget_ranges is None:
            return None
        return await self.budget_ranges.search(region, category=category, currency=currency)

    async def find(self, query: str, *, force_refresh: bool = False) -> InformationFinderOutput:
        normalized_query = normalize_query(query)
        warnings: list[str] = []
        embedding_available = True
        try:
            query_embedding = await self.embeddings.embed_query(normalized_query)
            identity = self.embeddings.identity
            local = await self.repository.retrieve(
                normalized_query,
                query_embedding,
                identity,
                self.options.retrieval_limit,
            )
        except EmbeddingProviderError as exc:
            # Web freshness queries must remain useful when the embedding
            # provider is rate-limited. Tavily results can still be ranked by
            # provider score and cited without pretending they have vectors.
            embedding_available = False
            query_embedding = None
            identity = None
            local = []
            warnings.append(f"embedding_fallback:{exc.code}")
        now = datetime.now(timezone.utc)
        fresh_local = list(local) if force_refresh else [
            source for source in local if source.expires_at > now
        ]
        decision = self.freshness.for_query(normalized_query)
        local_candidates = sorted(
            fresh_local,
            key=lambda source: source.semantic_score,
            reverse=True,
        )[: self.options.answer_source_limit]
        combined = list(local_candidates)
        should_search = force_refresh or decision.force_refresh
        search_queries: list[str] = []

        if self.search_query_planner is not None:
            try:
                search_plan = await self.search_query_planner.generate(
                    normalized_query,
                    local_candidates,
                )
                should_search = should_search or search_plan.should_search
                search_queries = search_plan.queries
            except SearchQueryPlanningError:
                warnings.append("search_query_planner_fallback")
                should_search = should_search or not local_candidates
        elif not local_candidates:
            should_search = True

        if should_search:
            if self.search_provider is None:
                warnings.append(
                    "Web search is not configured; the answer may use incomplete local sources."
                )
            else:
                if not search_queries:
                    search_queries = self._search_queries(normalized_query)
                failures: list[SearchProviderError] = []
                max_search_attempts = max(
                    1, min(self.options.max_tavily_attempts, 3)
                )
                for attempt, search_query in enumerate(
                    search_queries[:max_search_attempts], start=1
                ):
                    try:
                        response = await self.search_provider.search(search_query)
                        if embedding_available:
                            try:
                                prepared = await self._prepare_sources(
                                    response.results,
                                    query_embedding=query_embedding,
                                    expires_at=now + decision.ttl,
                                )
                                saved = await self.repository.save_search(
                                    original_query=query,
                                    normalized_query=normalized_query,
                                    sources=prepared,
                                    identity=identity,
                                    provider_request_id=response.provider_request_id,
                                    search_parameters={
                                        "forceRefresh": decision.force_refresh,
                                        "attempt": attempt,
                                        "searchQuery": search_query,
                                        "resultCount": len(response.results),
                                    },
                                )
                                self._score_saved_sources(
                                    saved,
                                    prepared,
                                    query_embedding,
                                    normalized_query,
                                )
                            except EmbeddingProviderError as exc:
                                embedding_available = False
                                query_embedding = None
                                identity = None
                                warnings.append(f"embedding_fallback:{exc.code}")
                                saved = self._sources_without_embeddings(
                                    response.results,
                                    expires_at=now + decision.ttl,
                                )
                        else:
                            saved = self._sources_without_embeddings(
                                response.results,
                                expires_at=now + decision.ttl,
                            )
                        combined.extend(source for source in saved)
                        if len(rank_sources(combined)) >= self.options.answer_source_limit:
                            break
                    except SearchProviderError as exc:
                        failures.append(exc)

                if failures:
                    error = failures[-1]
                    warnings.append(
                        f"Web search unavailable ({error.code}); local sources were used."
                    )
                    await self.repository.record_failed_search(
                        original_query=query,
                        normalized_query=normalized_query,
                        provider="tavily",
                        error_code=error.code,
                        search_parameters={
                            "forceRefresh": decision.force_refresh,
                            "attempts": len(failures),
                        },
                    )

        ranked = rank_sources(combined)[: self.options.answer_source_limit]
        if not ranked:
            return InformationFinderOutput(
                answer="Chưa có nguồn phù hợp để trả lời câu hỏi này.",
                warnings=[
                    *warnings,
                    "No source was available after local retrieval and optional web search.",
                ],
                metadata=AnswerMetadata(
                    generation_mode="none",
                    validation_status="no_sources",
                    confidence="unavailable",
                ),
            )
        used_extractive_fallback = False
        generation_mode = getattr(self.answers, "generation_mode", "structured")
        repair_attempted = False
        safe_no_answer = False
        rendered_answer = ""
        normalized_blocks = []
        try:
            generated = await self.answers.generate(normalized_query, ranked)
            invalid_ids = invalid_answer_source_ids(generated, ranked)
            if invalid_ids:
                logger.warning(
                    "information_finder_answer_invalid type=citation invalid_source_ids=%s",
                    invalid_ids,
                )
            repair = getattr(self.answers, "generate_repair", None)
            if invalid_ids and callable(repair):
                repair_attempted = True
                generated = await repair(normalized_query, ranked, invalid_ids)
                invalid_ids = invalid_answer_source_ids(generated, ranked)
            if invalid_ids:
                raise AnswerProviderInvalidOutput(
                    "answer cited unavailable source IDs"
                )
            rendered_answer, normalized_blocks, _ = validate_and_render_answer(
                generated, ranked
            )
        except Exception as exc:
            error_code = getattr(exc, "code", type(exc).__name__).lower()
            logger.warning(
                "information_finder_answer_failed stage=%s type=%s invalid_source_ids=%s",
                "repair" if repair_attempted else "initial",
                error_code,
                locals().get("invalid_ids", []),
            )
            repair = getattr(self.answers, "generate_repair", None)
            if not repair_attempted and callable(repair):
                try:
                    repair_attempted = True
                    generated = await repair(normalized_query, ranked, [])
                    if not invalid_answer_source_ids(generated, ranked):
                        rendered_answer, normalized_blocks, _ = validate_and_render_answer(
                            generated, ranked
                        )
                        warnings.append("answer_repair_succeeded")
                    else:
                        raise AnswerProviderInvalidOutput(
                            "answer repair cited unavailable source IDs"
                        )
                except Exception as repair_exc:
                    logger.warning(
                        "information_finder_answer_repair_failed type=%s invalid_source_ids=%s",
                        getattr(repair_exc, "code", type(repair_exc).__name__).lower(),
                        locals().get("invalid_ids", []),
                    )
                    warnings.append("answer_repair_failed")
            if not rendered_answer and self.options.answer_fallback_enabled and self.fallback_answers is not None:
                try:
                    generated = await self.fallback_answers.generate(normalized_query, ranked)
                    generation_mode = getattr(
                        self.fallback_answers, "generation_mode", "extractive"
                    )
                    rendered_answer, normalized_blocks, _ = validate_and_render_answer(
                        generated, ranked
                    )
                    used_extractive_fallback = True
                    warnings.append(f"answer_extractive_fallback:{error_code}")
                    logger.info("information_finder_extractive_fallback_succeeded source_count=%d", len(ranked))
                except Exception as fallback_exc:
                    logger.warning(
                        "information_finder_extractive_fallback_failed type=%s",
                        getattr(fallback_exc, "code", type(fallback_exc).__name__).lower(),
                    )
            elif not repair_attempted and not self.options.answer_fallback_enabled:
                raise
            elif not repair_attempted and self.fallback_answers is None:
                raise
            if not rendered_answer:
                safe_no_answer = True
                warnings.append("safe_no_answer:no_cited_content")

        if safe_no_answer:
            return InformationFinderOutput(
                answer="",
                facts=[],
                content_blocks=[],
                sources=[],
                suggestions=[],
                warnings=warnings,
                metadata=AnswerMetadata(
                    generation_mode="none",
                    validation_status="no_cited_content",
                    confidence="unavailable",
                    fallback_used=used_extractive_fallback,
                ),
            )

        rendered_answer = await link_verified_entities(
            rendered_answer,
            generated.entity_names,
            self.entity_resolver,
            generated.entity_candidates,
        )
        normalized_blocks = await materialize_entity_spans(
            normalized_blocks,
            entity_names=generated.entity_names,
            entity_candidates=generated.entity_candidates,
            resolver=self.entity_resolver,
        )

        source_by_id = {source.source_id: source for source in ranked}
        facts: list[AnswerClaim] = []
        cited_ids: list[str] = []
        for claim in generated.claims:
            if not claim.text.strip() or any(item not in source_by_id for item in claim.source_ids):
                continue
            facts.append(claim)
            cited_ids.extend(item for item in claim.source_ids if item not in cited_ids)
        for block in generated.blocks:
            for source_id in block_source_ids(block):
                if source_id in source_by_id and source_id not in cited_ids:
                    cited_ids.append(source_id)
        if not facts:
            warnings.append("No cited facts were extracted from available sources.")
        cited_sources = [source_by_id[item] for item in cited_ids]
        return InformationFinderOutput(
            answer=rendered_answer,
            facts=facts,
            content_blocks=normalized_blocks,
            entity_names=generated.entity_names,
            entity_candidates=generated.entity_candidates,
            sources=[self._citation(source) for source in cited_sources],
            suggestions=(
                []
                if used_extractive_fallback
                else suggestions_from_blocks(generated.blocks)
            ),
            warnings=warnings,
            metadata=build_answer_metadata(
                generation_mode=generation_mode,
                fallback_used=used_extractive_fallback,
                cited_sources=cited_sources,
                claim_count=len(facts),
            ),
        )

    def _search_queries(self, query: str) -> list[str]:
        candidates = [
            query,
            f"{query}; giới thiệu tổng quan địa phương và điểm đến du lịch",
            f"{query}; địa danh liên quan, lịch sử và điểm tham quan nổi bật",
        ]
        return candidates[: max(1, min(self.options.max_tavily_attempts, 3))]
