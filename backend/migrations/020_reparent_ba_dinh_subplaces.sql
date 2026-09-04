-- Model the Ba Dinh visit as one planner stop with three informational
-- SubPlaces. SubPlaces remain outside itinerary optimization and routing.
BEGIN;

DO $$
DECLARE
    required_id text;
BEGIN
    FOREACH required_id IN ARRAY ARRAY[
        'travel_place_ChIJuSIb5aOrNTERU_JW9ESZg4U',
        'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI',
        'subplace_hochiminh_fish_pond',
        'travel_place_ChIJm5BAy6arNTERO1z1B3z-0BU'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM knowledge_entities
            WHERE id = required_id
              AND entity_type IN ('TravelPlace', 'SubPlace')
        ) OR NOT EXISTS (
            SELECT 1
            FROM knowledge_properties
            WHERE entity_id = required_id AND key = 'latitude'
        ) OR NOT EXISTS (
            SELECT 1
            FROM knowledge_properties
            WHERE entity_id = required_id AND key = 'longitude'
        ) THEN
            RAISE EXCEPTION 'Ba Dinh SubPlace preflight failed for %', required_id;
        END IF;
    END LOOP;
END $$;

UPDATE knowledge_entities
SET entity_type = 'SubPlace', updated_at = now()
WHERE id = 'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI'
  AND entity_type <> 'SubPlace';

-- A SubPlace cannot itself own Has_Subplace edges. Flatten the three visit
-- points directly under Ba Dinh Square and remove any previous parent edge.
DELETE FROM knowledge_relationships
WHERE relationship_type = 'Has_Subplace'
  AND to_entity_id IN (
      'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI',
      'subplace_hochiminh_fish_pond',
      'travel_place_ChIJm5BAy6arNTERO1z1B3z-0BU'
  )
  AND from_entity_id <> 'travel_place_ChIJuSIb5aOrNTERU_JW9ESZg4U';

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
SELECT
    'travel_place_ChIJuSIb5aOrNTERU_JW9ESZg4U',
    'Has_Subplace',
    child_id,
    json_build_object('status', 'pending', 'priority', child_order),
    'https://www.vietnam.travel/things-to-do/11-must-see-attractions-ha-noi',
    'curated as a direct Ba Dinh visit point;verification=pending;' ||
        'batch=kg_ba_dinh_subplaces_v2_20260821',
    now(), now()
FROM (
    VALUES
        ('travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI', 100),
        ('subplace_hochiminh_fish_pond', 90),
        ('travel_place_ChIJm5BAy6arNTERO1z1B3z-0BU', 80)
) AS children(child_id, child_order)
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_entities(
    id, canonical_name, normalized_name, entity_type,
    status, created_at, updated_at
)
VALUES (
    'activity_ho_chi_minh_mausoleum_visit',
    'viếng Lăng Chủ tịch Hồ Chí Minh',
    'vieng lang chu tich ho chi minh',
    'ActivityItem',
    'pending', now(), now()
)
ON CONFLICT (id) DO UPDATE
SET canonical_name = EXCLUDED.canonical_name,
    normalized_name = EXCLUDED.normalized_name,
    entity_type = EXCLUDED.entity_type,
    updated_at = EXCLUDED.updated_at;

INSERT INTO knowledge_relationships(
    from_entity_id, relationship_type, to_entity_id,
    recommendations, source, source_note, created_at, updated_at
)
VALUES (
    'travel_place_ChIJF13BXqGrNTERTE3hz8KFDmI',
    'Offer_Item',
    'activity_ho_chi_minh_mausoleum_visit',
    json_build_object(
        'status', 'pending',
        'priority', 90,
        'action', 'visit',
        'displayTemplate', '{action} {item} tại {subplace}'
    ),
    'https://www.vietnam.travel/things-to-do/11-must-see-attractions-ha-noi',
    'curated;verification=pending;batch=kg_ba_dinh_subplaces_v2_20260821',
    now(), now()
)
ON CONFLICT (from_entity_id, relationship_type, to_entity_id) DO UPDATE
SET recommendations = EXCLUDED.recommendations,
    source = EXCLUDED.source,
    source_note = EXCLUDED.source_note,
    updated_at = EXCLUDED.updated_at;

COMMIT;
