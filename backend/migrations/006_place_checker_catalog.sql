BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS knowledge_entities_name_trgm_idx
    ON knowledge_entities USING gin (normalized_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS knowledge_aliases_name_trgm_idx
    ON knowledge_aliases USING gin (normalized_alias gin_trgm_ops);
CREATE INDEX IF NOT EXISTS knowledge_relationships_type_from_idx
    ON knowledge_relationships (relationship_type, from_entity_id);
CREATE INDEX IF NOT EXISTS knowledge_properties_key_entity_idx
    ON knowledge_properties (key, entity_id);

COMMIT;
