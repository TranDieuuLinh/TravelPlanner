STYLE_INTENT_RESOLUTION_SQL = """
WITH style_inputs(input_value) AS (
    SELECT unnest($1::text[])
), direct_styles AS (
    SELECT input.input_value,
           match.id AS style_id,
           match.canonical_name AS style_name
    FROM style_inputs input
    JOIN LATERAL (
        SELECT style.id, style.canonical_name,
               GREATEST(
                   similarity(style.normalized_name, input.input_value),
                   COALESCE(max(similarity(alias.normalized_alias, input.input_value)), 0)
               ) AS score
        FROM knowledge_entities style
        LEFT JOIN knowledge_aliases alias ON alias.entity_id = style.id
        WHERE style.entity_type = 'Style'
          AND style.status <> 'rejected'
          AND (
              style.normalized_name = input.input_value
              OR style.normalized_name % input.input_value
              OR alias.normalized_alias = input.input_value
              OR alias.normalized_alias % input.input_value
          )
        GROUP BY style.id
        HAVING GREATEST(
            similarity(style.normalized_name, input.input_value),
            COALESCE(max(similarity(alias.normalized_alias, input.input_value)), 0)
        ) >= 0.55
        ORDER BY score DESC, style.id
        LIMIT 1
    ) match ON true
), item_inputs(input_value) AS (
    SELECT unnest($2::text[])
), resolved_items AS (
    SELECT input.input_value,
           match.id AS item_id,
           match.canonical_name AS item_name
    FROM item_inputs input
    JOIN LATERAL (
        SELECT item.id, item.canonical_name,
               GREATEST(
                   similarity(item.normalized_name, input.input_value),
                   COALESCE(max(similarity(alias.normalized_alias, input.input_value)), 0)
               ) AS score
        FROM knowledge_entities item
        LEFT JOIN knowledge_aliases alias ON alias.entity_id = item.id
        WHERE item.entity_type IN (
            'FoodItem', 'DrinkItem', 'ActivityItem', 'ProductItem'
        )
          AND item.status <> 'rejected'
          AND (
              item.normalized_name = input.input_value
              OR item.normalized_name % input.input_value
              OR alias.normalized_alias = input.input_value
              OR alias.normalized_alias % input.input_value
          )
        GROUP BY item.id
        HAVING GREATEST(
            similarity(item.normalized_name, input.input_value),
            COALESCE(max(similarity(alias.normalized_alias, input.input_value)), 0)
        ) >= 0.55
        ORDER BY score DESC, item.id
        LIMIT 1
    ) match ON true
), item_styles AS (
    SELECT item.input_value,
           style.id AS style_id,
           style.canonical_name AS style_name,
           item.item_id,
           item.item_name
    FROM resolved_items item
    JOIN knowledge_relationships relation
      ON relation.from_entity_id = item.item_id
     AND relation.relationship_type = 'Has_Style'
    JOIN knowledge_entities style
      ON style.id = relation.to_entity_id
     AND style.entity_type = 'Style'
     AND style.status <> 'rejected'
)
SELECT 'style'::text AS request_source,
       input_value, style_id, style_name,
       NULL::text AS item_id, NULL::text AS item_name
FROM direct_styles
UNION ALL
SELECT 'item'::text, input_value, style_id, style_name, item_id, item_name
FROM item_styles
ORDER BY request_source, input_value, style_id, item_id NULLS FIRST
"""


STYLE_CANDIDATE_SQL = """
WITH RECURSIVE adm_descendants(id) AS (
    SELECT $1::text
    UNION
    SELECT child.from_entity_id
    FROM knowledge_relationships child
    JOIN adm_descendants parent ON parent.id = child.to_entity_id
    JOIN knowledge_entities entity ON entity.id = child.from_entity_id
    WHERE child.relationship_type = 'Located_In'
      AND entity.entity_type IN ('ADM0', 'ADM1', 'ADM2')
), active_styles AS (
    SELECT style.id, style.canonical_name
    FROM knowledge_entities style
    WHERE style.id = ANY($2::text[])
      AND style.entity_type = 'Style'
      AND style.status <> 'rejected'
), scoped_holders AS (
    SELECT DISTINCT holder.id, holder.canonical_name, holder.entity_type
    FROM knowledge_entities holder
    JOIN knowledge_relationships location
      ON location.from_entity_id = holder.id
     AND location.relationship_type = 'Located_In'
    WHERE holder.entity_type IN ('TravelPlace', 'Restaurant', 'DrinkDessert')
      AND holder.status <> 'rejected'
      AND location.to_entity_id IN (SELECT id FROM adm_descendants)
), style_items AS (
    SELECT style.id AS style_id,
           style.canonical_name AS style_name,
           item.id AS item_id,
           item.canonical_name AS item_name
    FROM active_styles style
    JOIN knowledge_relationships styled
      ON styled.to_entity_id = style.id
     AND styled.relationship_type = 'Has_Style'
    JOIN knowledge_entities item
      ON item.id = styled.from_entity_id
     AND item.entity_type IN (
         'FoodItem', 'DrinkItem', 'ActivityItem', 'ProductItem'
     )
     AND item.status <> 'rejected'
), raw_candidates AS (
    SELECT holder.id AS place_id,
           holder.canonical_name AS place_name,
           holder.entity_type,
           item.style_id,
           item.style_name,
           item.item_id,
           item.item_name,
           'Offer_Item'::text AS relationship_source
    FROM style_items item
    JOIN knowledge_relationships offered
      ON offered.to_entity_id = item.item_id
     AND offered.relationship_type = 'Offer_Item'
    JOIN scoped_holders holder ON holder.id = offered.from_entity_id
    WHERE COALESCE(offered.recommendations::jsonb->>'status', 'verified') <> 'rejected'
    UNION ALL
    SELECT holder.id,
           holder.canonical_name,
           holder.entity_type,
           style.id,
           style.canonical_name,
           NULL::text,
           NULL::text,
           'Has_Style'::text
    FROM active_styles style
    JOIN knowledge_relationships styled
      ON styled.to_entity_id = style.id
     AND styled.relationship_type = 'Has_Style'
    JOIN scoped_holders holder ON holder.id = styled.from_entity_id
    WHERE NOT EXISTS (
        SELECT 1 FROM style_items item WHERE item.style_id = style.id
    )
      AND COALESCE(styled.recommendations::jsonb->>'status', 'verified') <> 'rejected'
), ranked AS (
    SELECT candidate.*,
           row_number() OVER (
               PARTITION BY candidate.style_id
               ORDER BY
                   CASE candidate.relationship_source
                       WHEN 'Offer_Item' THEN 0 ELSE 1
                   END,
                   candidate.item_id NULLS LAST,
                   candidate.place_id
           ) AS style_rank
    FROM (
        SELECT DISTINCT ON (style_id, place_id, item_id)
               *
        FROM raw_candidates
        ORDER BY style_id, place_id, item_id NULLS LAST, relationship_source
    ) candidate
)
SELECT place_id, place_name, entity_type,
       style_id, style_name, item_id, item_name, relationship_source
FROM ranked
WHERE style_rank <= $3
ORDER BY style_id, style_rank, place_id
"""
