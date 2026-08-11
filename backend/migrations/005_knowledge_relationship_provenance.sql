BEGIN;

-- Keep relationship provenance available on fresh databases as well as the
-- current database, which already contains this column.
ALTER TABLE knowledge_relationships
    ADD COLUMN IF NOT EXISTS source_note text;

COMMIT;
