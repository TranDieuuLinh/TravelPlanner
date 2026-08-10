BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS information_finder_source_documents (
    id uuid PRIMARY KEY,
    canonical_url text NOT NULL UNIQUE,
    domain text NOT NULL,
    title text NOT NULL,
    provider text NOT NULL,
    review_status text NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS information_finder_source_snapshots (
    id uuid PRIMARY KEY,
    source_document_id uuid NOT NULL REFERENCES information_finder_source_documents(id),
    content text NOT NULL,
    content_hash char(64) NOT NULL,
    published_at timestamptz,
    source_updated_at timestamptz,
    last_fetched_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    provider_external_id text,
    provider_request_id text,
    extractor_version text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_document_id, content_hash)
);

CREATE TABLE IF NOT EXISTS information_finder_source_chunks (
    id uuid PRIMARY KEY,
    source_snapshot_id uuid NOT NULL REFERENCES information_finder_source_snapshots(id),
    chunk_index integer NOT NULL,
    content text NOT NULL,
    token_count integer NOT NULL,
    content_hash char(64) NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_snapshot_id, chunk_index),
    UNIQUE (source_snapshot_id, content_hash)
);

CREATE INDEX IF NOT EXISTS information_finder_chunks_fts_idx
    ON information_finder_source_chunks USING gin (search_vector);

CREATE TABLE IF NOT EXISTS information_finder_source_embeddings (
    id uuid PRIMARY KEY,
    source_chunk_id uuid NOT NULL REFERENCES information_finder_source_chunks(id),
    model_name text NOT NULL,
    model_revision text,
    dimensions integer NOT NULL CHECK (dimensions = 384),
    embedding vector(384) NOT NULL,
    embedded_at timestamptz NOT NULL,
    UNIQUE NULLS NOT DISTINCT (source_chunk_id, model_name, model_revision)
);

CREATE INDEX IF NOT EXISTS information_finder_embeddings_hnsw_idx
    ON information_finder_source_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS information_finder_search_runs (
    id uuid PRIMARY KEY,
    original_query text NOT NULL,
    normalized_query text NOT NULL,
    query_hash char(64) NOT NULL,
    provider text NOT NULL,
    provider_request_id text,
    search_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
    error_code text,
    searched_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS information_finder_search_run_sources (
    search_run_id uuid NOT NULL REFERENCES information_finder_search_runs(id),
    source_snapshot_id uuid NOT NULL REFERENCES information_finder_source_snapshots(id),
    rank integer NOT NULL,
    provider_score double precision,
    snippet text NOT NULL,
    PRIMARY KEY (search_run_id, source_snapshot_id)
);

COMMIT;
