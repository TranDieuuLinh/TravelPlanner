PLACE_SEARCH_SQL = """
WITH RECURSIVE adm_descendants(id) AS (
    SELECT $2::text
    UNION
    SELECT child.from_entity_id
    FROM knowledge_relationships child
    JOIN adm_descendants parent ON parent.id = child.to_entity_id
    JOIN knowledge_entities entity ON entity.id = child.from_entity_id
    WHERE child.relationship_type = 'Located_In'
      AND entity.entity_type IN ('ADM0', 'ADM1', 'ADM2')
), adm_ancestors(id) AS (
    SELECT $2::text
    UNION
    SELECT parent.to_entity_id
    FROM knowledge_relationships parent
    JOIN adm_ancestors child ON child.id = parent.from_entity_id
    JOIN knowledge_entities entity ON entity.id = parent.to_entity_id
    WHERE parent.relationship_type = 'Located_In'
      AND entity.entity_type IN ('ADM0', 'ADM1', 'ADM2')
), adm_scope(id) AS (
    SELECT id FROM adm_descendants
    UNION
    SELECT id FROM adm_ancestors
), scoped AS (
    SELECT DISTINCT entity.id
    FROM knowledge_entities entity
    JOIN knowledge_relationships location
      ON location.from_entity_id = entity.id
     AND location.relationship_type = 'Located_In'
    WHERE entity.entity_type = ANY($3::text[])
      AND location.to_entity_id IN (SELECT id FROM adm_descendants)
), lexical_hits AS (
    SELECT entity.id, similarity(entity.normalized_name, $1) AS preliminary_score
    FROM scoped
    JOIN knowledge_entities entity ON entity.id = scoped.id
    WHERE $1 <> '' AND entity.normalized_name % $1
    UNION ALL
    SELECT alias.entity_id, similarity(alias.normalized_alias, $1)
    FROM scoped
    JOIN knowledge_aliases alias ON alias.entity_id = scoped.id
    WHERE $1 <> '' AND alias.normalized_alias % $1
    UNION ALL
    SELECT relation.from_entity_id, similarity(target.normalized_name, $1)
    FROM scoped
    JOIN knowledge_relationships relation ON relation.from_entity_id = scoped.id
    JOIN knowledge_entities target ON target.id = relation.to_entity_id
    WHERE $1 <> ''
      AND relation.relationship_type IN ('Offer_Item', 'Has_Style')
      AND target.normalized_name % $1
    UNION ALL
    SELECT special.to_entity_id, 0.0
    FROM knowledge_relationships special
    JOIN scoped ON scoped.id = special.to_entity_id
    WHERE special.from_entity_id IN (SELECT id FROM adm_scope)
      AND special.relationship_type = 'Special_Experience'
    UNION ALL
    SELECT edge.to_entity_id, 0.0
    FROM knowledge_relationships edge
    JOIN scoped ON scoped.id = edge.to_entity_id
    WHERE $5::text IS NOT NULL
      AND edge.from_entity_id = $5::text
      AND edge.relationship_type IN ('Special_Near', 'Near', 'Must_Visit')
    UNION ALL
    SELECT edge.from_entity_id, 0.0
    FROM knowledge_relationships edge
    JOIN scoped ON scoped.id = edge.from_entity_id
    WHERE $5::text IS NOT NULL
      AND edge.to_entity_id = $5::text
      AND edge.relationship_type IN ('Special_Near', 'Near', 'Must_Visit')
), candidate_ids AS (
    SELECT id, max(preliminary_score) AS preliminary_score
    FROM lexical_hits
    GROUP BY id
    HAVING max(preliminary_score) >= $6 OR max(preliminary_score) = 0
    ORDER BY max(preliminary_score) DESC, id
    LIMIT $4
)
SELECT entity.id, entity.canonical_name, entity.entity_type, entity.status,
       aliases.values AS aliases,
       props.address, props.latitude, props.longitude,
       props.rating, props.review_count, props.updated_at,
       tags.values AS tags,
       COALESCE(relevance.score, 0) AS relationship_score,
       CASE WHEN relevance.kind IS NULL THEN NULL
            ELSE 'relation:' || lower(relevance.kind) END AS anchor_relation,
       COALESCE(relations.values, '[]'::jsonb) AS relationship_evidence,
       GREATEST(
           candidate_ids.preliminary_score,
           similarity(entity.normalized_name, $1),
           COALESCE(aliases.score, 0),
           COALESCE(tags.score, 0)
       ) AS match_score
FROM candidate_ids
JOIN knowledge_entities entity ON entity.id = candidate_ids.id
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT alias.alias) AS values,
           max(similarity(alias.normalized_alias, $1)) AS score
    FROM knowledge_aliases alias WHERE alias.entity_id = entity.id
) aliases ON true
LEFT JOIN LATERAL (
    SELECT
        max(property.value) FILTER (WHERE property.key = 'address') AS address,
        max(property.value) FILTER (WHERE property.key = 'latitude') AS latitude,
        max(property.value) FILTER (WHERE property.key = 'longitude') AS longitude,
        max(property.value) FILTER (WHERE property.key = 'rating') AS rating,
        max(property.value) FILTER (WHERE property.key = 'review_count') AS review_count,
        max(property.updated_at) AS updated_at
    FROM knowledge_properties property WHERE property.entity_id = entity.id
) props ON true
LEFT JOIN LATERAL (
    SELECT array_agg(DISTINCT label) AS values, max(label_score) AS score
    FROM (
        SELECT CASE relation.relationship_type
                   WHEN 'Offer_Item' THEN 'item:' || target.canonical_name
                   WHEN 'Has_Style' THEN 'style:' || target.canonical_name
               END AS label,
               similarity(target.normalized_name, $1) AS label_score
        FROM knowledge_relationships relation
        JOIN knowledge_entities target ON target.id = relation.to_entity_id
        WHERE relation.from_entity_id = entity.id
          AND relation.relationship_type IN ('Offer_Item', 'Has_Style')
        UNION ALL
        SELECT 'experience:special_experience', 0.0
        FROM knowledge_relationships relation
        JOIN knowledge_entities area ON area.id = relation.from_entity_id
        WHERE relation.to_entity_id = entity.id
          AND relation.relationship_type = 'Special_Experience'
          AND relation.from_entity_id IN (SELECT id FROM adm_scope)
    ) labels
) tags ON true
LEFT JOIN LATERAL (
    SELECT kind, score
    FROM (
        SELECT edge.relationship_type AS kind,
               CASE edge.relationship_type
                   WHEN 'Must_Visit' THEN 0.95
                   WHEN 'Near' THEN 0.85
                   WHEN 'Special_Near' THEN GREATEST(
                       0.65,
                       0.95 - 0.30 * COALESCE(
                           (edge.recommendations::jsonb->>'distance_km')::double precision
                           / NULLIF((edge.recommendations::jsonb->>'threshold_km')::double precision, 0),
                           1
                       )
                   )
                   ELSE 0
               END AS score
        FROM knowledge_relationships edge
        WHERE $5::text IS NOT NULL
          AND ((edge.from_entity_id = $5 AND edge.to_entity_id = entity.id)
            OR (edge.from_entity_id = entity.id AND edge.to_entity_id = $5))
          AND edge.relationship_type IN ('Special_Near', 'Near', 'Must_Visit')
        UNION ALL
        SELECT special.relationship_type,
               CASE WHEN special.recommendations::jsonb->>'status' = 'pending'
                    THEN 0.55 ELSE 0.78 END
        FROM knowledge_relationships special
        WHERE special.to_entity_id = entity.id
          AND special.from_entity_id IN (SELECT id FROM adm_scope)
          AND special.relationship_type = 'Special_Experience'
        UNION ALL
        SELECT relation.relationship_type,
               CASE relation.relationship_type
                   WHEN 'Offer_Item' THEN COALESCE(
                       CASE jsonb_typeof(relation.recommendations::jsonb)
                           WHEN 'array' THEN (
                               SELECT max((evidence->>'confidence')::double precision)
                               FROM jsonb_array_elements(relation.recommendations::jsonb) evidence
                               WHERE evidence ? 'confidence'
                           )
                           WHEN 'object' THEN
                               (relation.recommendations::jsonb->>'confidence')::double precision
                       END,
                       CASE WHEN relation.recommendations::jsonb->>'status' = 'pending'
                            THEN 0.45 ELSE 0.72 END
                   )
                   WHEN 'Has_Style' THEN LEAST(
                       0.75,
                       0.45 + COALESCE(
                           (relation.recommendations::jsonb->>'priority')::double precision / 400,
                           0.10
                       )
                   )
               END
        FROM knowledge_relationships relation
        JOIN knowledge_entities target ON target.id = relation.to_entity_id
        WHERE relation.from_entity_id = entity.id
          AND relation.relationship_type IN ('Offer_Item', 'Has_Style')
          AND target.normalized_name % $1
    ) scored_relations
    ORDER BY score DESC, kind
    LIMIT 1
) relevance ON true
LEFT JOIN LATERAL (
    SELECT jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
        'relationshipType', edge.relationship_type,
        'direction', edge.direction,
        'scope', edge.scope,
        'fromEntityId', edge.from_entity_id,
        'toEntityId', edge.to_entity_id,
        'relatedEntityId', edge.related_entity_id,
        'relatedName', edge.related_name,
        'status', edge.status,
        'confidence', edge.confidence,
        'priority', edge.priority,
        'distanceKm', edge.distance_km,
        'thresholdKm', edge.threshold_km,
        'source', edge.source,
        'sourceNote', edge.source_note,
        'properties', edge.properties,
        'score', edge.score
    )) ORDER BY edge.score DESC, edge.relationship_type, edge.related_entity_id) AS values
    FROM (
        SELECT relation.relationship_type, 'place_to_attribute' AS direction,
               'place' AS scope, relation.from_entity_id, relation.to_entity_id,
               relation.to_entity_id AS related_entity_id,
               target.canonical_name AS related_name,
               CASE WHEN jsonb_typeof(relation.recommendations::jsonb) = 'object'
                    THEN relation.recommendations::jsonb->>'status' END AS status,
               CASE WHEN relation.relationship_type = 'Offer_Item' THEN
                   CASE jsonb_typeof(relation.recommendations::jsonb)
                       WHEN 'array' THEN (
                           SELECT max((evidence->>'confidence')::double precision)
                           FROM jsonb_array_elements(relation.recommendations::jsonb) evidence
                           WHERE evidence ? 'confidence'
                       )
                       WHEN 'object' THEN
                           (relation.recommendations::jsonb->>'confidence')::double precision
                   END
               END AS confidence,
               CASE WHEN jsonb_typeof(relation.recommendations::jsonb) = 'object'
                    THEN (relation.recommendations::jsonb->>'priority')::double precision END AS priority,
               NULL::double precision AS distance_km,
               NULL::double precision AS threshold_km,
               relation.source, relation.source_note,
               CASE WHEN relation.relationship_type = 'Has_Style'
                    THEN COALESCE(relation.recommendations::jsonb->'properties', '{}'::jsonb)
                    ELSE '{}'::jsonb END AS properties,
               CASE relation.relationship_type
                   WHEN 'Offer_Item' THEN COALESCE(
                       CASE jsonb_typeof(relation.recommendations::jsonb)
                           WHEN 'array' THEN (
                               SELECT max((evidence->>'confidence')::double precision)
                               FROM jsonb_array_elements(relation.recommendations::jsonb) evidence
                               WHERE evidence ? 'confidence'
                           )
                           WHEN 'object' THEN
                               (relation.recommendations::jsonb->>'confidence')::double precision
                       END,
                       0.72
                   )
                   ELSE LEAST(0.75, 0.45 + COALESCE(
                       (relation.recommendations::jsonb->>'priority')::double precision / 400,
                       0.10
                   ))
               END AS score
        FROM knowledge_relationships relation
        JOIN knowledge_entities target ON target.id = relation.to_entity_id
        WHERE relation.from_entity_id = entity.id
          AND relation.relationship_type IN ('Offer_Item', 'Has_Style')
        UNION ALL
        SELECT relation.relationship_type, 'area_to_place', 'destination',
               relation.from_entity_id, relation.to_entity_id,
               relation.from_entity_id, area.canonical_name,
               relation.recommendations::jsonb->>'status', NULL, NULL, NULL, NULL,
               relation.source, relation.source_note, '{}'::jsonb,
               CASE WHEN relation.recommendations::jsonb->>'status' = 'pending' THEN 0.55 ELSE 0.78 END
        FROM knowledge_relationships relation
        JOIN knowledge_entities area ON area.id = relation.from_entity_id
        WHERE relation.to_entity_id = entity.id
          AND relation.relationship_type = 'Special_Experience'
          AND relation.from_entity_id IN (SELECT id FROM adm_scope)
        UNION ALL
        SELECT relation.relationship_type, 'place_to_place', 'anchor',
               relation.from_entity_id, relation.to_entity_id,
               CASE WHEN relation.from_entity_id = entity.id
                    THEN relation.to_entity_id ELSE relation.from_entity_id END,
               related.canonical_name, NULL, NULL, NULL,
               (relation.recommendations::jsonb->>'distance_km')::double precision,
               (relation.recommendations::jsonb->>'threshold_km')::double precision,
               relation.source, relation.source_note, '{}'::jsonb,
               CASE relation.relationship_type
                   WHEN 'Must_Visit' THEN 0.95 WHEN 'Near' THEN 0.85
                   ELSE GREATEST(0.65, 0.95 - 0.30 * COALESCE(
                       (relation.recommendations::jsonb->>'distance_km')::double precision
                       / NULLIF((relation.recommendations::jsonb->>'threshold_km')::double precision, 0), 1))
               END
        FROM knowledge_relationships relation
        JOIN knowledge_entities related ON related.id = CASE
            WHEN relation.from_entity_id = entity.id THEN relation.to_entity_id
            ELSE relation.from_entity_id END
        WHERE $5::text IS NOT NULL
          AND ((relation.from_entity_id = $5 AND relation.to_entity_id = entity.id)
            OR (relation.from_entity_id = entity.id AND relation.to_entity_id = $5))
          AND relation.relationship_type IN ('Special_Near', 'Near', 'Must_Visit')
    ) edge
) relations ON true
ORDER BY relationship_score DESC, match_score DESC,
         NULLIF(props.rating, '')::double precision DESC NULLS LAST,
         NULLIF(props.review_count, '')::bigint DESC NULLS LAST,
         entity.canonical_name
LIMIT $4
"""
