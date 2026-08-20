from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Literal
from urllib.parse import urlsplit

from app.modules.information_finder.contract import (
    InformationFinderOutput, AnswerClaim,
    PreparedChunk,
    PreparedSource,
    RetrievedSource,
    SourceReference,
)
from app.modules.information_finder.errors import (
    EmbeddingProviderError,
    SearchQueryPlanningError,
    SourceChunkingError,
)
from app.modules.information_finder.entity_linking import EntityResolver
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
from app.modules.information_finder.utils import (
    canonicalize_url,
    chunk_content,
    content_hash,
    normalize_query,
)
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


DETERMINISTIC_CHUNKING_VERSION = "deterministic-v1"


class InformationFinderService:
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

    async def find(self, query: str) -> InformationFinderOutput:
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
        fresh_local = [source for source in local if source.expires_at > now]
        decision = self.freshness.for_query(normalized_query)
        local_candidates = sorted(
            fresh_local,
            key=lambda source: source.semantic_score,
            reverse=True,
        )[: self.options.answer_source_limit]
        combined = list(local_candidates)
        should_search = decision.force_refresh
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
            )
        used_extractive_fallback = False
        try:
            generated = await self.answers.generate(normalized_query, ranked)
        except Exception:
            if not self.options.answer_fallback_enabled or self.fallback_answers is None:
                raise
            generated = await self.fallback_answers.generate(normalized_query, ranked)
            used_extractive_fallback = True
            warnings.append("answer_extractive_fallback:fact_extraction")

        source_by_id = {source.source_id: source for source in ranked}
        facts: list[AnswerClaim] = []
        cited_ids: list[str] = []
        for claim in generated.claims:
            if not claim.text.strip() or any(item not in source_by_id for item in claim.source_ids):
                continue
            facts.append(claim)
            cited_ids.extend(item for item in claim.source_ids if item not in cited_ids)
        for block in generated.blocks:
            for source_id in self._block_source_ids(block):
                if source_id in source_by_id and source_id not in cited_ids:
                    cited_ids.append(source_id)
        if not facts:
            warnings.append("No cited facts were extracted from available sources.")
        return InformationFinderOutput(
            facts=facts,
            # Fallback blocks are source excerpts, not presentation-ready
            # answers. Keep them private so the supervisor composer can
            # normalize the facts before the API exposes the response.
            content_blocks=[] if used_extractive_fallback else generated.blocks,
            sources=[self._citation(source_by_id[item]) for item in cited_ids],
            suggestions=(
                []
                if used_extractive_fallback
                else self._suggestions_from_blocks(generated.blocks)
            ),
            warnings=warnings,
        )

    @staticmethod
    def _block_source_ids(block) -> list[str]:
        ids = list(getattr(block, "source_ids", []))
        for field in ("items", "options"):
            for item in getattr(block, field, []):
                ids.extend(getattr(item, "source_ids", []))
        return ids

    @classmethod
    def _suggestions_from_blocks(cls, blocks) -> list[dict[str, object]]:
        """Turn retrieved, cited recommendations into grounded chat choices."""
        suggestions: list[dict[str, object]] = []
        for block in blocks:
            if getattr(block, "type", None) not in {"recommendations", "comparison"}:
                continue
            entries = getattr(block, "items", None) or getattr(block, "options", None) or []
            for entry in entries[:5]:
                name = str(getattr(entry, "name", "")).strip()
                source_ids = list(dict.fromkeys(getattr(entry, "source_ids", [])))
                if not name or not source_ids:
                    continue
                suggestions.append({
                    "field": "information_follow_up",
                    "label": name,
                    "value": f"Cho tôi biết thêm về {name}",
                    "sourceIds": source_ids,
                })
        return suggestions

    @staticmethod
    def _sources_without_embeddings(
        results,
        *,
        expires_at: datetime,
        minimum_content_chars: int = 80,
        provider_relevance_threshold: float = 0.5,
    ) -> list[RetrievedSource]:
        """Keep usable Tavily results when vector generation is unavailable."""
        sources: list[RetrievedSource] = []
        seen_urls: set[str] = set()
        for result in results:
            try:
                url = canonicalize_url(result.url)
            except ValueError:
                continue
            if (
                len(result.content.strip()) < minimum_content_chars
                or (result.provider_score or 0.0) < provider_relevance_threshold
                or url in seen_urls
            ):
                continue
            seen_urls.add(url)
            source_key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
            sources.append(
                RetrievedSource(
                    source_id=f"tavily-{source_key}",
                    snapshot_id=f"tavily-{source_key}",
                    title=result.title,
                    url=url,
                    content=result.content,
                    semantic_score=0.0,
                    lexical_score=0.0,
                    freshness_score=1.0,
                    provider_score=result.provider_score,
                    published_at=result.published_at,
                    source_updated_at=result.source_updated_at,
                    last_fetched_at=result.fetched_at,
                    expires_at=expires_at,
                )
            )
        return sources

    async def _prepare_sources(
        self,
        results,
        *,
        query_embedding: list[float],
        expires_at: datetime,
    ) -> list[PreparedSource]:
        accepted = []
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        for result in results:
            try:
                canonical_url = canonicalize_url(result.url)
            except ValueError:
                continue
            domain = urlsplit(canonical_url).hostname or ""
            digest = content_hash(result.content)
            score = result.provider_score if result.provider_score is not None else 0.0
            if (
                len(result.content.strip()) < self.options.minimum_content_chars
                or score < self.options.provider_relevance_threshold
                or any(
                    domain == blocked or domain.endswith(f".{blocked}")
                    for blocked in self.options.blocked_domains
                )
                or canonical_url in seen_urls
                or digest in seen_hashes
            ):
                continue
            seen_urls.add(canonical_url)
            seen_hashes.add(digest)
            accepted.append((result, canonical_url, domain, digest))

        chunk_sets: list[tuple[list[tuple[str, int]], str]] = []
        for result, *_ in accepted:
            chunking_version = DETERMINISTIC_CHUNKING_VERSION
            if self.chunker is not None:
                try:
                    semantic_chunks = await self.chunker.chunk(result)
                    source_chunks = [
                        (chunk, len(chunk.split())) for chunk in semantic_chunks
                    ]
                    chunking_version = self.chunker.version
                except SourceChunkingError:
                    source_chunks = chunk_content(
                        result.content,
                        title=result.title,
                        target_tokens=self.options.chunk_tokens,
                        overlap_tokens=self.options.chunk_overlap,
                    )
            else:
                source_chunks = chunk_content(
                    result.content,
                    title=result.title,
                    target_tokens=self.options.chunk_tokens,
                    overlap_tokens=self.options.chunk_overlap,
                )
            chunk_sets.append((source_chunks, chunking_version))
        texts = [chunk for source_chunks, _ in chunk_sets for chunk, _ in source_chunks]
        vectors = await self.embeddings.embed_documents(texts) if texts else []
        vector_index = 0
        prepared_sources: list[PreparedSource] = []
        embedded_at = datetime.now(timezone.utc)
        for (result, canonical_url, domain, digest), (
            source_chunks,
            chunking_version,
        ) in zip(accepted, chunk_sets):
            prepared_chunks: list[PreparedChunk] = []
            for index, (chunk, token_count) in enumerate(source_chunks):
                prepared_chunks.append(
                    PreparedChunk(
                        chunk_index=index,
                        content=chunk,
                        token_count=token_count,
                        content_hash=content_hash(chunk),
                        embedding=vectors[vector_index],
                        embedded_at=embedded_at,
                    )
                )
                vector_index += 1
            prepared_sources.append(
                PreparedSource(
                    result=result,
                    canonical_url=canonical_url,
                    domain=domain,
                    content_hash=digest,
                    expires_at=expires_at,
                    chunks=prepared_chunks,
                    chunking_version=chunking_version,
                )
            )
        return prepared_sources

    @staticmethod
    def _score_saved_sources(
        saved: list[RetrievedSource],
        prepared: list[PreparedSource],
        query_embedding: list[float],
        query: str,
    ) -> None:
        query_terms = set(query.casefold().split())
        for source, prepared_source in zip(saved, prepared):
            source.semantic_score = max(
                (
                    sum(a * b for a, b in zip(query_embedding, chunk.embedding))
                    for chunk in prepared_source.chunks
                ),
                default=0.0,
            )
            content_terms = set(source.content.casefold().split())
            source.lexical_score = len(query_terms & content_terms) / max(
                1, len(query_terms)
            )
            source.freshness_score = 1.0

    @staticmethod
    def _citation(source: RetrievedSource) -> SourceReference:
        if source.source_updated_at is not None:
            updated_at = source.source_updated_at
            date_kind: Literal["source_updated_at", "last_fetched_at"] = (
                "source_updated_at"
            )
        else:
            updated_at = source.last_fetched_at
            date_kind = "last_fetched_at"
        return SourceReference(
            source_id=source.source_id,
            title=source.title,
            url=source.url,
            updated_at=updated_at,
            date_kind=date_kind,
            review_status=source.review_status,
            published_at=source.published_at,
        )

    def _search_queries(self, query: str) -> list[str]:
        candidates = [
            query,
            f"{query}; giới thiệu tổng quan địa phương và điểm đến du lịch",
            f"{query}; địa danh liên quan, lịch sử và điểm tham quan nổi bật",
        ]
        return candidates[: max(1, min(self.options.max_tavily_attempts, 3))]
