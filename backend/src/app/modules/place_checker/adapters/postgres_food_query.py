SPECIAL_FOOD_RESTAURANT_SQL = """
WITH RECURSIVE adm_descendants(id) AS (
    SELECT $1::text
    UNION
    SELECT child.from_entity_id
    FROM knowledge_relationships child
    JOIN adm_descendants parent ON parent.id = child.to_entity_id
    JOIN knowledge_entities entity ON entity.id = child.from_entity_id
    WHERE child.relationship_type = 'Located_In'
      AND entity.entity_type IN ('ADM0', 'ADM1', 'ADM2')
), scoped_restaurants AS (
    SELECT DISTINCT restaurant.id, restaurant.canonical_name
    FROM knowledge_entities restaurant
    JOIN knowledge_relationships location
      ON location.from_entity_id = restaurant.id
     AND location.relationship_type = 'Located_In'
    WHERE restaurant.entity_type = 'Restaurant'
      AND restaurant.status <> 'rejected'
      AND location.to_entity_id IN (SELECT id FROM adm_descendants)
      AND NOT (restaurant.id = ANY($5::text[]))
), anchor_coordinates AS (
    SELECT anchor.anchor_place_id,
           NULLIF(max(property.value) FILTER (
               WHERE property.key = 'latitude'
           ), '')::double precision AS latitude,
           NULLIF(max(property.value) FILTER (
               WHERE property.key = 'longitude'
           ), '')::double precision AS longitude
    FROM unnest($2::text[]) AS anchor(anchor_place_id)
    LEFT JOIN knowledge_properties property
      ON property.entity_id = anchor.anchor_place_id
    GROUP BY anchor.anchor_place_id
), restaurant_coordinates AS (
    SELECT restaurant.id AS restaurant_id,
           restaurant.canonical_name AS restaurant_name,
           NULLIF(max(property.value) FILTER (
               WHERE property.key = 'latitude'
           ), '')::double precision AS latitude,
           NULLIF(max(property.value) FILTER (
               WHERE property.key = 'longitude'
           ), '')::double precision AS longitude
    FROM scoped_restaurants restaurant
    LEFT JOIN knowledge_properties property
      ON property.entity_id = restaurant.id
    GROUP BY restaurant.id, restaurant.canonical_name
), distance_pairs AS (
    SELECT anchor.anchor_place_id,
           restaurant.restaurant_id,
           restaurant.restaurant_name,
           6371.0 * 2.0 * asin(sqrt(LEAST(1.0,
               power(sin(radians(
                   (restaurant.latitude - anchor.latitude) / 2.0
               )), 2)
               + cos(radians(anchor.latitude))
               * cos(radians(restaurant.latitude))
               * power(sin(radians(
                   (restaurant.longitude - anchor.longitude) / 2.0
               )), 2)
           ))) AS distance_km
    FROM anchor_coordinates anchor
    CROSS JOIN restaurant_coordinates restaurant
    WHERE anchor.latitude IS NOT NULL
      AND anchor.longitude IS NOT NULL
      AND restaurant.latitude IS NOT NULL
      AND restaurant.longitude IS NOT NULL
), proximity_evidence AS (
    SELECT pair.*,
           edge.has_special_near,
           edge.edge_threshold_km,
           row_number() OVER (
               PARTITION BY pair.anchor_place_id
               ORDER BY pair.distance_km, pair.restaurant_id
           ) AS proximity_rank
    FROM distance_pairs pair
    LEFT JOIN LATERAL (
        SELECT bool_or(true) AS has_special_near,
               min(NULLIF(
                   relation.recommendations::jsonb->>'threshold_km', ''
               )::double precision) AS edge_threshold_km
        FROM knowledge_relationships relation
        WHERE relation.relationship_type = 'Special_Near'
          AND (
              (relation.from_entity_id = pair.anchor_place_id
               AND relation.to_entity_id = pair.restaurant_id)
              OR
              (relation.to_entity_id = pair.anchor_place_id
               AND relation.from_entity_id = pair.restaurant_id)
          )
    ) edge ON true
    WHERE $3::double precision IS NULL OR pair.distance_km <= $3
), nearby_restaurants AS (
    SELECT *
    FROM proximity_evidence
    WHERE proximity_rank <= LEAST(120, GREATEST(40, $4 * 10))
), special_foods AS (
    SELECT food.id AS food_item_id,
           food.canonical_name AS food_item_name,
           LEAST(1.0, GREATEST(0.0, COALESCE(
               NULLIF(special.recommendations::jsonb->>'priority', '')::double precision
                   / 100.0,
               0.50
           ))) AS food_priority,
           LEAST(1.0, GREATEST(0.0, COALESCE(
               NULLIF(special.recommendations::jsonb->>'confidence', '')::double precision,
               0.70
           ))) AS food_confidence
    FROM knowledge_relationships special
    JOIN knowledge_entities food ON food.id = special.to_entity_id
    WHERE special.from_entity_id = $1
      AND special.relationship_type = 'Special_Experience'
      AND food.entity_type IN ('FoodItem', 'DrinkItem')
      AND COALESCE(special.recommendations::jsonb->>'status', 'verified') <> 'rejected'
), food_evidence AS (
    SELECT relation.from_entity_id AS restaurant_id,
           special_food.food_item_id,
           special_food.food_item_name,
           NULL::text AS style_id,
           NULL::text AS style_name,
           special_food.food_priority,
           special_food.food_confidence,
           special_food.food_item_id AS offered_food_item_id,
           special_food.food_item_name AS offered_food_item_name,
           'special_experience'::text AS food_match_type,
           1.0::double precision AS food_match_confidence,
           0.70::double precision AS offer_confidence
    FROM knowledge_relationships relation
    JOIN special_foods special_food
      ON special_food.food_item_id = relation.to_entity_id
    WHERE relation.relationship_type = 'Special_Experience'
      AND COALESCE(relation.recommendations::jsonb->>'status', 'verified') <> 'rejected'
    UNION ALL
    SELECT offer.from_entity_id,
           food.id,
           food.canonical_name,
           NULL::text,
           NULL::text,
           0.35::double precision,
           0.70::double precision,
           food.id,
           food.canonical_name,
           'offer_item'::text,
           1.0::double precision,
           0.70::double precision
    FROM knowledge_relationships offer
    JOIN knowledge_entities food
      ON food.id = offer.to_entity_id
     AND food.entity_type IN ('FoodItem', 'DrinkItem')
    WHERE offer.relationship_type = 'Offer_Item'
      AND COALESCE(offer.recommendations::jsonb->>'status', 'verified') <> 'rejected'
), ranked_pairs AS (
    SELECT nearby.anchor_place_id,
           nearby.restaurant_id,
           nearby.restaurant_name,
           nearby.distance_km,
           COALESCE(nearby.edge_threshold_km, 5.0) AS threshold_km,
           evidence.food_item_id,
           evidence.food_item_name,
           evidence.style_id,
           evidence.style_name,
           evidence.offered_food_item_id,
           evidence.offered_food_item_name,
           evidence.food_match_type,
           evidence.food_match_confidence,
           evidence.food_priority,
           evidence.food_confidence,
           evidence.offer_confidence,
           CASE
               WHEN nearby.has_special_near AND nearby.distance_km <= 5.0 THEN 'both'
               WHEN nearby.has_special_near THEN 'kg_special_near'
               WHEN nearby.distance_km <= 5.0 THEN 'computed_distance'
               ELSE 'general_adm'
           END AS proximity_source,
           row_number() OVER (
               PARTITION BY nearby.anchor_place_id,
                            evidence.food_item_id
               ORDER BY nearby.distance_km,
                        evidence.food_item_id,
                        nearby.restaurant_id
           ) AS style_rank
    FROM nearby_restaurants nearby
    JOIN food_evidence evidence ON evidence.restaurant_id = nearby.restaurant_id
)
SELECT anchor_place_id,
       restaurant_id,
       restaurant_name,
       distance_km,
       threshold_km,
       food_item_id,
       food_item_name,
       style_id,
       style_name,
       offered_food_item_id,
       offered_food_item_name,
       food_match_type,
       food_match_confidence,
       food_priority,
       food_confidence,
       offer_confidence,
       proximity_source
FROM ranked_pairs
WHERE style_rank <= LEAST($4, 4)
ORDER BY anchor_place_id,
         style_rank,
         food_item_id,
         restaurant_id
"""
