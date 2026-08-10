from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from app.modules.information_finder.contract import (
    InformationFinderOutput,
    PreparedChunk,
    PreparedSource,
    RetrievedSource,
    SourceReference,
)
from app.modules.information_finder.freshness import FreshnessPolicy
from app.modules.information_finder.ports import (
    AnswerGenerator,
    EmbeddingProvider,
    SearchProvider,
    SearchProviderError,
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
    similarity_threshold: float = 0.65
    provider_relevance_threshold: float = 0.5
    minimum_content_chars: int = 80
    blocked_domains: tuple[str, ...] = ()
    chunk_tokens: int = 300
    chunk_overlap: int = 50


class InformationFinderService:
    def __init__(
        self,
        *,
        repository: SourceRepository,
        embeddings: EmbeddingProvider,
        answers: AnswerGenerator,
        search_provider: SearchProvider | None = None,
        freshness: FreshnessPolicy | None = None,
        options: InformationFinderOptions | None = None,
    ) -> None:
        self.repository = repository
        self.embeddings = embeddings
        self.answers = answers
        self.search_provider = search_provider
        self.freshness = freshness or FreshnessPolicy()
        self.options = options or InformationFinderOptions()

    async def find(self, query: str) -> InformationFinderOutput:
        normalized_query = normalize_query(query)
        query_embedding = await self.embeddings.embed_query(normalized_query)
        identity = self.embeddings.identity
        local = await self.repository.retrieve(
            normalized_query,
            query_embedding,
            identity,
            self.options.retrieval_limit,
        )
        now = datetime.now(timezone.utc)
        fresh_local = [source for source in local if source.expires_at > now]
        decision = self.freshness.for_query(normalized_query)
        local_sufficient = has_sufficient_local_sources(
            fresh_local,
            minimum_sources=self.options.minimum_local_sources,
            similarity_threshold=self.options.similarity_threshold,
            minimum_content_chars=self.options.minimum_content_chars,
        )
        warnings: list[str] = []
        combined = list(fresh_local)

        if decision.force_refresh or not local_sufficient:
            if self.search_provider is None:
                warnings.append(
                    "Web search is not configured; the answer may use incomplete local sources."
                )
            else:
                try:
                    response = await self.search_provider.search(normalized_query)
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
                            "resultCount": len(response.results),
                        },
                    )
                    self._score_saved_sources(
                        saved,
                        prepared,
                        query_embedding,
                        normalized_query,
                    )
                    combined.extend(saved)
                except SearchProviderError as exc:
                    warnings.append(f"Web search unavailable ({exc.code}); local sources were used.")
                    await self.repository.record_failed_search(
                        original_query=query,
                        normalized_query=normalized_query,
                        provider="tavily",
                        error_code=exc.code,
                        search_parameters={"forceRefresh": decision.force_refresh},
                    )

        ranked = rank_sources(combined)[: self.options.answer_source_limit]
        answer = await self.answers.generate(normalized_query, ranked)
        return InformationFinderOutput(
            answer=answer,
            sources=[self._citation(source) for source in ranked],
            warnings=warnings,
        )

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
                or any(domain == blocked or domain.endswith(f".{blocked}") for blocked in self.options.blocked_domains)
                or canonical_url in seen_urls
                or digest in seen_hashes
            ):
                continue
            seen_urls.add(canonical_url)
            seen_hashes.add(digest)
            accepted.append((result, canonical_url, domain, digest))

        chunk_sets = [
            chunk_content(
                result.content,
                title=result.title,
                target_tokens=self.options.chunk_tokens,
                overlap_tokens=self.options.chunk_overlap,
            )
            for result, *_ in accepted
        ]
        texts = [chunk for chunks in chunk_sets for chunk, _ in chunks]
        vectors = await self.embeddings.embed_documents(texts) if texts else []
        vector_index = 0
        prepared_sources = []
        embedded_at = datetime.now(timezone.utc)
        for (result, canonical_url, domain, digest), chunks in zip(accepted, chunk_sets):
            prepared_chunks = []
            for index, (chunk, token_count) in enumerate(chunks):
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
