-- Reclassify camping and horse-riding venues as Entertainment.
-- Market/local-trading activity venues remain TravelPlace.
-- Entity IDs and graph relationships are preserved.
BEGIN;

WITH outdoor_items AS (
    SELECT id
    FROM knowledge_entities
    WHERE entity_type = 'ActivityItem'
      AND canonical_name IN ('Cắm trại', 'Cưỡi ngựa')
), candidates AS (
    SELECT DISTINCT e.id
    FROM knowledge_entities e
    JOIN knowledge_relationships r
      ON r.from_entity_id = e.id
     AND r.relationship_type = 'Offer_Item'
    JOIN outdoor_items i ON i.id = r.to_entity_id
    WHERE e.entity_type = 'TravelPlace'
)
UPDATE knowledge_entities e
SET entity_type = 'Entertainment',
    updated_at = now()
FROM candidates c
WHERE e.id = c.id;

COMMIT;
