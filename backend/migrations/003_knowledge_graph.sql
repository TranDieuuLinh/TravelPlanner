BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_entities (
    id text PRIMARY KEY,
    canonical_name text NOT NULL,
    normalized_name text NOT NULL,
    entity_type text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    review_count integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE knowledge_entities ADD COLUMN IF NOT EXISTS review_count integer;

CREATE INDEX IF NOT EXISTS knowledge_entities_name_idx
    ON knowledge_entities (normalized_name);
CREATE INDEX IF NOT EXISTS knowledge_entities_type_status_idx
    ON knowledge_entities (entity_type, status);

CREATE TABLE IF NOT EXISTS knowledge_aliases (
    id bigserial PRIMARY KEY,
    entity_id text NOT NULL REFERENCES knowledge_entities(id) ON DELETE CASCADE,
    alias text NOT NULL,
    normalized_alias text NOT NULL,
    language text NOT NULL DEFAULT 'und',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_aliases_entity_idx ON knowledge_aliases(entity_id);
CREATE INDEX IF NOT EXISTS knowledge_aliases_normalized_idx ON knowledge_aliases(normalized_alias);

CREATE TABLE IF NOT EXISTS knowledge_properties (
    id bigserial PRIMARY KEY,
    entity_id text NOT NULL REFERENCES knowledge_entities(id) ON DELETE CASCADE,
    key text NOT NULL,
    value text NOT NULL,
    source text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_properties_entity_idx ON knowledge_properties(entity_id);

CREATE TABLE IF NOT EXISTS knowledge_relationships (
    id bigserial PRIMARY KEY,
    from_entity_id text NOT NULL REFERENCES knowledge_entities(id) ON DELETE CASCADE,
    relationship_type text NOT NULL,
    to_entity_id text NOT NULL REFERENCES knowledge_entities(id) ON DELETE CASCADE,
    recommendations jsonb,
    source text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS knowledge_relationships_from_idx
    ON knowledge_relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS knowledge_relationships_to_idx
    ON knowledge_relationships(to_entity_id);

COMMIT;
