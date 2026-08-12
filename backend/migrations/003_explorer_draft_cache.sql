BEGIN;

CREATE TABLE IF NOT EXISTS explorer_draft_cache (
    cache_key varchar NOT NULL PRIMARY KEY,
    namespace varchar NOT NULL,
    draft json NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_explorer_draft_cache_namespace_updated_at
    ON explorer_draft_cache (namespace, updated_at);

COMMENT ON TABLE explorer_draft_cache IS
    'Explorer-owned cache for synthesized drafts keyed by normalized evidence.';

COMMIT;
