from datetime import datetime, timezone
import hashlib
from typing import Literal
from urllib.parse import urlsplit

from app.modules.information_finder.contract import (
    PreparedChunk,
    PreparedSource,
    RetrievedSource,
    SourceReference,
)
from app.modules.information_finder.errors import SourceChunkingError
from app.modules.information_finder.utils import (
    canonicalize_url,
    chunk_content,
    content_hash,
)


DETERMINISTIC_CHUNKING_VERSION = "deterministic-v1"


class SourceProcessingMixin:
    """Source preparation owned by the Information Finder retrieval flow."""

    @staticmethod
    def _sources_without_embeddings(
        results,
        *,
        expires_at: datetime,
        minimum_content_chars: int = 80,
        provider_relevance_threshold: float = 0.5,
    ) -> list[RetrievedSource]:
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
        texts = [chunk for chunks, _ in chunk_sets for chunk, _ in chunks]
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
