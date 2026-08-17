import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from app.modules.information_finder.contract import (
    EmbeddingIdentity,
    PreparedSource,
    RetrievedSource,
)
from app.modules.information_finder.freshness import FreshnessPolicy
from app.shared.observability import traced_call


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.9g}" for value in values) + "]"


class PostgresSourceRepository:
    """Owns only the information_finder_* tables created by its migration."""

    def __init__(self, database_url: str, *, command_timeout: float = 15.0) -> None:
        self.database_url = database_url
        self.command_timeout = command_timeout
        self._pool = None

    async def _get_pool(self):
        if self._pool is None:
            try:
                import asyncpg  # type: ignore[import-untyped]
            except ImportError as exc:
                raise RuntimeError(
                    "asyncpg is required for PostgreSQL source cache"
                ) from exc
            self._pool = await asyncpg.create_pool(
                self.database_url,
                command_timeout=self.command_timeout,
                min_size=0,
                max_size=1,
            )
        return self._pool

    async def retrieve(
        self,
        query: str,
        query_embedding: list[float],
        identity: EmbeddingIdentity,
        limit: int,
    ) -> list[RetrievedSource]:
        return await traced_call(
            "information_finder.postgres.retrieve",
            lambda: self._retrieve(query, query_embedding, identity, limit),
            kind="database",
            input_summary={
                "queryChars": len(query),
                "embeddingDimensions": len(query_embedding),
                "limit": limit,
            },
            output_summary=lambda value: {
                "sourceCount": len(value),
                "cacheHit": bool(value),
            },
            metadata={"module": "information_finder", "provider": "postgres"},
        )

    async def _retrieve(
        self,
        query: str,
        query_embedding: list[float],
        identity: EmbeddingIdentity,
        limit: int,
    ) -> list[RetrievedSource]:
        pool = await self._get_pool()
        sql = """
            WITH scored AS (
                SELECT d.id AS source_id, s.id AS snapshot_id, d.title,
                       d.canonical_url, c.content, d.review_status,
                       s.published_at, s.source_updated_at, s.last_fetched_at,
                       s.expires_at,
                       1 - (e.embedding <=> $1::vector) AS semantic_score,
                       ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', $2))
                           AS lexical_score,
                       row_number() OVER (
                           PARTITION BY d.id
                           ORDER BY (e.embedding <=> $1::vector), c.chunk_index
                       ) AS source_rank
                FROM information_finder_source_embeddings e
                JOIN information_finder_source_chunks c ON c.id = e.source_chunk_id
                JOIN information_finder_source_snapshots s ON s.id = c.source_snapshot_id
                JOIN information_finder_source_documents d ON d.id = s.source_document_id
                WHERE e.model_name = $3
                  AND e.model_revision IS NOT DISTINCT FROM $4
                  AND e.dimensions = $5
                  AND d.review_status <> 'rejected'
            )
            SELECT * FROM scored WHERE source_rank = 1
            ORDER BY (0.65 * semantic_score + 0.25 * lexical_score) DESC
            LIMIT $6
        """
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                sql,
                _vector_literal(query_embedding),
                query,
                identity.model_name,
                identity.model_revision,
                identity.dimensions,
                limit,
            )
        return [self._to_source(row) for row in rows]

    async def save_search(
        self,
        *,
        original_query: str,
        normalized_query: str,
        sources: list[PreparedSource],
        identity: EmbeddingIdentity,
        provider_request_id: str | None,
        search_parameters: dict,
    ) -> list[RetrievedSource]:
        return await traced_call(
            "information_finder.postgres.save_search",
            lambda: self._save_search(
                original_query=original_query,
                normalized_query=normalized_query,
                sources=sources,
                identity=identity,
                provider_request_id=provider_request_id,
                search_parameters=search_parameters,
            ),
            kind="database",
            input_summary={"sourceCount": len(sources)},
            output_summary=lambda value: {"savedSourceCount": len(value)},
            metadata={"module": "information_finder", "provider": "postgres"},
        )

    async def _save_search(
        self,
        *,
        original_query: str,
        normalized_query: str,
        sources: list[PreparedSource],
        identity: EmbeddingIdentity,
        provider_request_id: str | None,
        search_parameters: dict,
    ) -> list[RetrievedSource]:
        pool = await self._get_pool()
        async with pool.acquire() as connection, connection.transaction():
            run_id = uuid4()
            await connection.execute(
                """INSERT INTO information_finder_search_runs
                   (id, original_query, normalized_query, query_hash, provider,
                    provider_request_id, search_parameters, status, searched_at, expires_at)
                   VALUES ($1,$2,$3,$4,'tavily',$5,$6::jsonb,'succeeded',now(),$7)""",
                run_id,
                original_query,
                normalized_query,
                hashlib.sha256(normalized_query.encode()).hexdigest(),
                provider_request_id,
                json.dumps(search_parameters),
                max(
                    (source.expires_at for source in sources),
                    default=datetime.now(timezone.utc),
                ),
            )
            saved = []
            for rank, source in enumerate(sources, start=1):
                saved_source = await self._upsert_source(connection, source, identity)
                saved.append(saved_source)
                await connection.execute(
                    """INSERT INTO information_finder_search_run_sources
                       (search_run_id, source_snapshot_id, rank, provider_score, snippet)
                       VALUES ($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING""",
                    run_id,
                    saved_source.snapshot_id,
                    rank,
                    source.result.provider_score,
                    source.result.content[:1000],
                )
            return saved

    async def _upsert_source(self, connection, source, identity):
        document_id = uuid4()
        row = await connection.fetchrow(
            """INSERT INTO information_finder_source_documents
               (id, canonical_url, domain, title, provider, review_status)
               VALUES ($1,$2,$3,$4,$5,'pending')
               ON CONFLICT (canonical_url) DO UPDATE SET
                 title=EXCLUDED.title, updated_at=now()
               RETURNING id, review_status""",
            document_id,
            source.canonical_url,
            source.domain,
            source.result.title,
            source.result.provider,
        )
        document_id = row["id"]
        existing_snapshot = await connection.fetchrow(
            """SELECT id, content_hash, extractor_version
               FROM information_finder_source_snapshots
               WHERE source_document_id=$1 AND content_hash=$2 FOR UPDATE""",
            document_id,
            source.content_hash,
        )
        if existing_snapshot:
            snapshot_id = existing_snapshot["id"]
            await connection.execute(
                """UPDATE information_finder_source_snapshots SET
                   last_fetched_at=$2, expires_at=$3,
                   source_updated_at=COALESCE($4, source_updated_at),
                   extractor_version=$5, updated_at=now()
                   WHERE id=$1""",
                snapshot_id,
                source.result.fetched_at,
                source.expires_at,
                source.result.source_updated_at,
                source.chunking_version,
            )
            if existing_snapshot["extractor_version"] != source.chunking_version:
                await self._replace_chunks(
                    connection, snapshot_id, source.chunks, identity
                )
        else:
            snapshot_id = uuid4()
            await connection.execute(
                """INSERT INTO information_finder_source_snapshots
                   (id, source_document_id, content, content_hash, published_at,
                    source_updated_at, last_fetched_at, expires_at,
                    provider_external_id, provider_request_id, extractor_version)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)""",
                snapshot_id,
                document_id,
                source.result.content,
                source.content_hash,
                source.result.published_at,
                source.result.source_updated_at,
                source.result.fetched_at,
                source.expires_at,
                source.result.provider_external_id,
                source.result.provider_request_id,
                source.chunking_version,
            )
            await self._replace_chunks(connection, snapshot_id, source.chunks, identity)
        return RetrievedSource(
            source_id=str(document_id),
            snapshot_id=str(snapshot_id),
            title=source.result.title,
            url=source.canonical_url,
            content=source.result.content,
            semantic_score=source.result.provider_score or 0.0,
            provider_score=source.result.provider_score,
            published_at=source.result.published_at,
            source_updated_at=source.result.source_updated_at,
            last_fetched_at=source.result.fetched_at,
            expires_at=source.expires_at,
            review_status=row["review_status"],
        )

    @staticmethod
    async def _replace_chunks(connection, snapshot_id, chunks, identity) -> None:
        await connection.execute(
            """DELETE FROM information_finder_source_embeddings
               WHERE source_chunk_id IN (
                 SELECT id FROM information_finder_source_chunks
                 WHERE source_snapshot_id=$1
               )""",
            snapshot_id,
        )
        await connection.execute(
            "DELETE FROM information_finder_source_chunks WHERE source_snapshot_id=$1",
            snapshot_id,
        )
        for chunk in chunks:
            chunk_id = uuid4()
            await connection.execute(
                """INSERT INTO information_finder_source_chunks
                   (id, source_snapshot_id, chunk_index, content, token_count, content_hash)
                   VALUES ($1,$2,$3,$4,$5,$6)""",
                chunk_id,
                snapshot_id,
                chunk.chunk_index,
                chunk.content,
                chunk.token_count,
                chunk.content_hash,
            )
            await connection.execute(
                """INSERT INTO information_finder_source_embeddings
                   (id, source_chunk_id, model_name, model_revision, dimensions,
                    embedding, embedded_at) VALUES ($1,$2,$3,$4,$5,$6::vector,$7)""",
                uuid4(),
                chunk_id,
                identity.model_name,
                identity.model_revision,
                identity.dimensions,
                _vector_literal(chunk.embedding),
                chunk.embedded_at,
            )

    async def record_failed_search(self, **kwargs) -> None:
        pool = await self._get_pool()
        normalized = kwargs["normalized_query"]
        async with pool.acquire() as connection:
            await connection.execute(
                """INSERT INTO information_finder_search_runs
                   (id, original_query, normalized_query, query_hash, provider,
                    search_parameters, status, error_code, searched_at, expires_at)
                   VALUES ($1,$2,$3,$4,$5,$6::jsonb,'failed',$7,now(),now())""",
                uuid4(),
                kwargs["original_query"],
                normalized,
                hashlib.sha256(normalized.encode()).hexdigest(),
                kwargs["provider"],
                json.dumps(kwargs["search_parameters"]),
                kwargs["error_code"],
            )

    @staticmethod
    def _to_source(row) -> RetrievedSource:
        return RetrievedSource(
            source_id=str(row["source_id"]),
            snapshot_id=str(row["snapshot_id"]),
            title=row["title"],
            url=row["canonical_url"],
            content=row["content"],
            semantic_score=float(row["semantic_score"] or 0),
            lexical_score=float(row["lexical_score"] or 0),
            freshness_score=FreshnessPolicy.score(row["expires_at"]),
            published_at=row["published_at"],
            source_updated_at=row["source_updated_at"],
            last_fetched_at=row["last_fetched_at"],
            expires_at=row["expires_at"],
            review_status=row["review_status"],
        )
