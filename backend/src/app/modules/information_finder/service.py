from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from typing import Literal
from urllib.parse import urlsplit

from app.modules.information_finder.contract import (
    InformationFinderOutput,
    PreparedChunk,
    PreparedSource,
    RetrievedSource,
    SourceReference,
)
from app.modules.information_finder.answering import validate_and_render_answer
from app.modules.information_finder.errors import (
    AnswerProviderError,
    EmbeddingProviderError,
    SearchQueryPlanningError,
    SourceChunkingError,
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
from app.modules.information_finder.ranking import (
    has_sufficient_local_sources,
    rank_sources,
)
from app.modules.information_finder.utils import (
    canonicalize_url,
    chunk_content,
    content_hash,
    normalize_query,
)


@dataclass(frozen=True)
class InformationFinderOptions:
    retrieval_limit: int = 10
    answer_source_limit: int = 5
    minimum_local_sources: int = 2
    similarity_threshold: float = 0.8
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
        freshness: FreshnessPolicy | None = None,
        options: InformationFinderOptions | None = None,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.answers = answers
        self.fallback_answers = fallback_answers
        self.chunker = chunker
        self.search_provider = search_provider
        self.search_query_planner = search_query_planner
        self.freshness = freshness or FreshnessPolicy()
        self.options = options or InformationFinderOptions()

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
        fresh_local = [
            source
            for source in local
            if source.expires_at > now
            and source.semantic_score >= self.options.similarity_threshold
        ]
        decision = self.freshness.for_query(normalized_query)
        local_sufficient = has_sufficient_local_sources(
            fresh_local,
            query=normalized_query,
            minimum_sources=self.options.minimum_local_sources,
            similarity_threshold=self.options.similarity_threshold,
            minimum_content_chars=self.options.minimum_content_chars,
            topic_overlap_threshold=self.options.topic_overlap_threshold,
        )
        combined = list(fresh_local)

        if decision.force_refresh or not local_sufficient:
            if self.search_provider is None:
                warnings.append(
                    "Web search is not configured; the answer may use incomplete local sources."
                )
            else:
                search_queries = self._search_queries(normalized_query)
                if self.search_query_planner is not None:
                    try:
                        search_queries = await self.search_query_planner.generate(
                            normalized_query
                        )
                    except SearchQueryPlanningError:
                        warnings.append("search_query_planner_fallback")
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
                        combined.extend(
                            source
                            for source in saved
                            if not embedding_available
                            or source.semantic_score >= self.options.similarity_threshold
                        )
                        if not embedding_available and len(combined) >= self.options.minimum_local_sources:
                            break
                        if has_sufficient_local_sources(
                            combined,
                            query=normalized_query,
                            minimum_sources=self.options.minimum_local_sources,
                            similarity_threshold=self.options.similarity_threshold,
                            minimum_content_chars=self.options.minimum_content_chars,
                            topic_overlap_threshold=self.options.topic_overlap_threshold,
                        ):
                            break
                    except SearchProviderError as exc:
                        failures.append(exc)

                if failures and not combined:
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
                    "No source met the semantic similarity threshold.",
                ],
            )
        try:
            generated = await self.answers.generate(normalized_query, ranked)
            answer, cited_sources = validate_and_render_answer(generated, ranked)
        except AnswerProviderError as exc:
            if (
                not self.options.answer_fallback_enabled
                or self.fallback_answers is None
            ):
                raise
            fallback = await self.fallback_answers.generate(normalized_query, ranked)
            answer, cited_sources = validate_and_render_answer(fallback, ranked)
            warnings.append(f"answer_extractive_fallback:{exc.code}")
        return InformationFinderOutput(
            answer=answer,
            sources=[self._citation(source) for source in cited_sources],
            warnings=warnings,
        )

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
