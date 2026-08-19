BEGIN;

CREATE TABLE IF NOT EXISTS source_documents (
    id varchar NOT NULL PRIMARY KEY,
    canonical_url text NOT NULL,
    platform varchar NOT NULL,
    artifacts json NOT NULL,
    extracted_context json NOT NULL,
    artifact_hash varchar,
    extractor_version varchar,
    fetched_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_source_documents_canonical_url
    ON source_documents (canonical_url);

CREATE INDEX IF NOT EXISTS ix_source_documents_platform_fetched_at
    ON source_documents (platform, fetched_at);

COMMENT ON TABLE source_documents IS
    'Explorer-owned normalized URL extraction cache adopted from old_one.';

COMMIT;
