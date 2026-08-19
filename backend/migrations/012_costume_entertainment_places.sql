-- Reclassify places dedicated to cosplay/costume activities as Entertainment.
-- This preserves entity IDs and all existing graph relationships.
BEGIN;

WITH costume_items AS (
    SELECT id
    FROM knowledge_entities
    WHERE entity_type = 'ActivityItem'
      AND (
          canonical_name ILIKE ANY (ARRAY['%cosplay%', '%hóa trang%', '%hoa trang%']::text[])
          OR normalized_name ILIKE ANY (ARRAY['%cosplay%', '%hoa trang%']::text[])
      )
), candidates AS (
    SELECT DISTINCT e.id
    FROM knowledge_entities e
    WHERE e.entity_type = 'TravelPlace'
      AND (
          e.canonical_name ILIKE ANY (ARRAY['%cosplay%', '%hóa trang%', '%hoa trang%']::text[])
          OR e.normalized_name ILIKE ANY (ARRAY['%cosplay%', '%hoa trang%']::text[])
          OR EXISTS (
              SELECT 1
              FROM knowledge_relationships r
              JOIN costume_items i ON i.id = r.to_entity_id
              WHERE r.from_entity_id = e.id
                AND r.relationship_type = 'Offer_Item'
          )
      )
)
UPDATE knowledge_entities e
SET entity_type = 'Entertainment',
    updated_at = now()
FROM candidates c
WHERE e.id = c.id;

COMMIT;
