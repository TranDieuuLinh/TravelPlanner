"""Unified identity lookup for places explicitly named by the traveler."""

NAMED_PLACE_SEARCH_SQL = """
WITH RECURSIVE adm_descendants(id) AS (
    SELECT $2::text
    UNION
    SELECT child.from_entity_id
    FROM knowledge_relationships child
    JOIN adm_descendants parent ON parent.id = child.to_entity_id
    JOIN knowledge_entities entity ON entity.id = child.from_entity_id
    WHERE child.relationship_type = 'Located_In'
      AND entity.entity_type IN ('ADM0', 'ADM1', 'ADM2')
), scoped AS (
    SELECT DISTINCT entity.id
    FROM knowledge_entities entity
    JOIN knowledge_relationships location
      ON location.from_entity_id = entity.id
     AND location.relationship_type = 'Located_In'
    WHERE entity.entity_type = ANY($3::text[])
      AND entity.status <> 'rejected'
      AND location.to_entity_id IN (SELECT id FROM adm_descendants)
), candidate_ids AS (
    SELECT entity.id,
           GREATEST(
               similarity(entity.normalized_name, $1),
               COALESCE(max(similarity(alias.normalized_alias, $1)), 0),
               COALESCE(max(similarity(lower(address.value), lower($6))), 0)
           ) AS preliminary_score
    FROM scoped
    JOIN knowledge_entities entity ON entity.id = scoped.id
    LEFT JOIN knowledge_aliases alias ON alias.entity_id = entity.id
    LEFT JOIN knowledge_properties address
      ON address.entity_id = entity.id
     AND address.key = 'address'
    WHERE entity.normalized_name % $1
       OR alias.normalized_alias % $1
       OR entity.normalized_name = $1
       OR alias.normalized_alias = $1
       OR (
           $6::text IS NOT NULL
           AND lower(address.value) % lower($6)
       )
    GROUP BY entity.id
    HAVING GREATEST(
        similarity(entity.normalized_name, $1),
        COALESCE(max(similarity(alias.normalized_alias, $1)), 0),
        COALESCE(max(similarity(lower(address.value), lower($6))), 0)
    ) >= $5
    ORDER BY preliminary_score DESC, entity.id
    LIMIT $4
)
SELECT entity.id, entity.canonical_name, entity.entity_type, entity.status,
       (
           entity.status <> 'verified'
           AND EXISTS (
               SELECT 1 FROM knowledge_properties review_property
               WHERE review_property.entity_id = entity.id
                 AND review_property.note LIKE
                     'provider=google_maps_playwright;verification=not_verified%'
           )
       ) AS requires_admin_review,
       aliases.values AS aliases,
       props.address, props.latitude, props.longitude,
       props.rating, props.review_count, props.updated_at,
       ARRAY[]::text[] AS tags,
       0.0::double precision AS relationship_score,
       NULL::text AS anchor_relation,
       '[]'::jsonb AS relationship_evidence,
       candidate_ids.preliminary_score AS match_score
FROM candidate_ids
JOIN knowledge_entities entity ON entity.id = candidate_ids.id
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT alias.alias) AS values
    FROM knowledge_aliases alias
    WHERE alias.entity_id = entity.id
) aliases ON true
LEFT JOIN LATERAL (
    SELECT
        max(property.value) FILTER (WHERE property.key = 'address') AS address,
        max(property.value) FILTER (WHERE property.key = 'latitude') AS latitude,
        max(property.value) FILTER (WHERE property.key = 'longitude') AS longitude,
        max(property.value) FILTER (WHERE property.key = 'rating') AS rating,
        max(property.value) FILTER (WHERE property.key = 'review_count') AS review_count,
        max(property.updated_at) AS updated_at
    FROM knowledge_properties property
    WHERE property.entity_id = entity.id
) props ON true
ORDER BY candidate_ids.preliminary_score DESC, entity.id
"""
