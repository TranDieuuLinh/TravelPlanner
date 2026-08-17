-- Reclassify the reviewed non-travel place candidates as Entertainment.
-- Expected preflight on 2026-08-17: 451 TravelPlace rows match; all IDs and
-- relationship rows must remain unchanged. The predicate is intentionally
-- idempotent: rows already classified as Entertainment are not updated again.
BEGIN;

UPDATE knowledge_entities
SET entity_type = 'Entertainment',
    updated_at = now()
WHERE entity_type = 'TravelPlace'
  AND (
    canonical_name ILIKE ANY (ARRAY[
      '%spa%', '%massage%', '%billiard%', '%billard%', '%bida%',
      '%karaoke%', '%gym%', '%fitness%', '%nail%'
    ]::text[])
    OR normalized_name ILIKE ANY (ARRAY[
      '%spa%', '%massage%', '%billiard%', '%billard%', '%bida%',
      '%karaoke%', '%gym%', '%fitness%', '%nail%'
    ]::text[])
  );

COMMIT;
