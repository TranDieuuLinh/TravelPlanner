PLACE_SEARCH_SQL = """
WITH scoped AS (
    SELECT DISTINCT e.id
    FROM knowledge_entities e
    JOIN knowledge_relationships location
      ON location.from_entity_id = e.id
     AND location.relationship_type = 'Located_In'
    LEFT JOIN knowledge_relationships parent
      ON parent.from_entity_id = location.to_entity_id
     AND parent.relationship_type = 'Located_In'
    WHERE e.entity_type = ANY($3::text[])
      AND (location.to_entity_id = $2 OR parent.to_entity_id = $2)
), lexical_hits AS (
    SELECT e.id, similarity(e.normalized_name, $1) AS preliminary_score
    FROM scoped s
    JOIN knowledge_entities e ON e.id = s.id
    WHERE $1 <> '' AND e.normalized_name % $1
    UNION ALL
    SELECT a.entity_id, similarity(a.normalized_alias, $1)
    FROM scoped s
    JOIN knowledge_aliases a ON a.entity_id = s.id
    WHERE $1 <> '' AND a.normalized_alias % $1
    UNION ALL
    SELECT r.from_entity_id, similarity(target.normalized_name, $1)
    FROM scoped s
    JOIN knowledge_relationships r ON r.from_entity_id = s.id
    JOIN knowledge_entities target ON target.id = r.to_entity_id
    WHERE $1 <> ''
      AND r.relationship_type IN ('Special_Experience', 'Offer_Item', 'Has_Style')
      AND target.normalized_name % $1
    UNION ALL
    SELECT edge.to_entity_id, 0.0
    FROM knowledge_relationships edge
    JOIN scoped s ON s.id = edge.to_entity_id
    WHERE $5::text IS NOT NULL
      AND edge.from_entity_id = $5::text
      AND edge.relationship_type IN (
          'Special_Near', 'Special_Experience', 'Offer_Item', 'Has_Style'
      )
    UNION ALL
    SELECT edge.from_entity_id, 0.0
    FROM knowledge_relationships edge
    JOIN scoped s ON s.id = edge.from_entity_id
    WHERE $5::text IS NOT NULL
      AND edge.to_entity_id = $5::text
      AND edge.relationship_type IN (
          'Special_Near', 'Special_Experience', 'Offer_Item', 'Has_Style'
      )
), candidate_ids AS (
    SELECT id, max(preliminary_score) AS preliminary_score
    FROM lexical_hits
    GROUP BY id
    HAVING max(preliminary_score) >= $6 OR max(preliminary_score) = 0
    ORDER BY max(preliminary_score) DESC, id
    LIMIT $4
)
SELECT e.id, e.canonical_name, e.entity_type, e.status,
       aliases.values AS aliases,
       props.address, props.latitude, props.longitude,
       props.rating, props.review_count, props.updated_at,
       tags.values AS tags,
       CASE relation.kind
           WHEN 'Special_Near' THEN 0.95
           WHEN 'Special_Experience' THEN 0.75
           WHEN 'Offer_Item' THEN 0.72
           WHEN 'Has_Style' THEN 0.55
           ELSE 0
       END AS relationship_score,
       CASE WHEN relation.kind IS NULL THEN NULL
            ELSE 'relation:' || lower(relation.kind) END AS anchor_relation,
       GREATEST(
           candidate_ids.preliminary_score,
           similarity(e.normalized_name, $1),
           COALESCE(aliases.score, 0),
           COALESCE(tags.score, 0)
       ) AS match_score
FROM candidate_ids
JOIN knowledge_entities e ON e.id = candidate_ids.id
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT a.alias) AS values,
           max(similarity(a.normalized_alias, $1)) AS score
    FROM knowledge_aliases a WHERE a.entity_id = e.id
) aliases ON true
LEFT JOIN LATERAL (
    SELECT
        max(p.value) FILTER (WHERE p.key = 'address') AS address,
        max(p.value) FILTER (WHERE p.key = 'latitude') AS latitude,
        max(p.value) FILTER (WHERE p.key = 'longitude') AS longitude,
        max(p.value) FILTER (WHERE p.key = 'rating') AS rating,
        max(p.value) FILTER (WHERE p.key = 'review_count') AS review_count,
        max(p.updated_at) AS updated_at
    FROM knowledge_properties p WHERE p.entity_id = e.id
) props ON true
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT
               CASE r.relationship_type
                   WHEN 'Special_Experience' THEN 'experience:' || target.canonical_name
                   WHEN 'Offer_Item' THEN 'item:' || target.canonical_name
                   WHEN 'Has_Style' THEN 'style:' || target.canonical_name
                   ELSE 'relation:' || lower(r.relationship_type)
               END
           ) AS values,
           max(similarity(target.normalized_name, $1)) AS score
    FROM knowledge_relationships r
    JOIN knowledge_entities target ON target.id = r.to_entity_id
    WHERE r.from_entity_id = e.id
      AND r.relationship_type IN ('Special_Experience', 'Offer_Item', 'Has_Style')
) tags ON true
LEFT JOIN LATERAL (
    SELECT edge.relationship_type AS kind
    FROM knowledge_relationships edge
    WHERE $5::text IS NOT NULL
      AND (
          (edge.from_entity_id = $5::text AND edge.to_entity_id = e.id)
          OR (edge.from_entity_id = e.id AND edge.to_entity_id = $5::text)
      )
      AND edge.relationship_type IN (
          'Special_Near', 'Special_Experience', 'Offer_Item', 'Has_Style'
      )
    ORDER BY CASE edge.relationship_type
        WHEN 'Special_Near' THEN 1
        WHEN 'Special_Experience' THEN 2 WHEN 'Offer_Item' THEN 3 ELSE 4 END
    LIMIT 1
) relation ON true
ORDER BY relationship_score DESC, match_score DESC,
         NULLIF(props.rating, '')::double precision DESC NULLS LAST,
         NULLIF(props.review_count, '')::bigint DESC NULLS LAST,
         e.canonical_name
LIMIT $4
"""
