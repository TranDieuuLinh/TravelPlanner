-- Rename the legacy must-visit relationship and remove the obsolete near edge.
BEGIN;

UPDATE knowledge_relationships
SET relationship_type = 'Special_Near', updated_at = now()
WHERE relationship_type = 'Must_Visit';

DELETE FROM knowledge_relationships
WHERE relationship_type = 'Near';

COMMIT;
