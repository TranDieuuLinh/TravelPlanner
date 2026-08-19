-- Temporarily remove duplicated time properties from place-like and venue nodes.
-- The canonical time data is kept on Style nodes. Style properties are untouched.
BEGIN;

DELETE FROM knowledge_properties p
USING knowledge_entities e
WHERE p.entity_id = e.id
  AND e.entity_type IN ('TravelPlace', 'Entertainment', 'DrinkDessert', 'Restaurant')
  AND p.key IN ('time_duration', 'time_windows');

COMMIT;
