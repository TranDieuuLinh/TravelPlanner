SPECIAL_FOOD_RESTAURANT_SQL = """
WITH special_foods AS (
    SELECT food.id AS food_item_id,
           food.canonical_name AS food_item_name,
           COALESCE(
               NULLIF(special.recommendations::jsonb->>'priority', '')::double precision,
               50
           ) AS food_priority,
           COALESCE(
               NULLIF(special.recommendations::jsonb->>'confidence', '')::double precision,
               0.70
           ) AS food_confidence
    FROM knowledge_relationships special
    JOIN knowledge_entities food ON food.id = special.to_entity_id
    WHERE special.from_entity_id = $1
      AND special.relationship_type = 'Special_Experience'
      AND food.entity_type = 'FoodItem'
      AND COALESCE(special.recommendations::jsonb->>'status', 'verified') <> 'rejected'
), nearby_restaurants AS (
    SELECT anchor.anchor_place_id,
           restaurant.id AS restaurant_id,
           restaurant.canonical_name AS restaurant_name,
           NULLIF(near_edge.recommendations::jsonb->>'distance_km', '')::double precision
               AS distance_km,
           NULLIF(near_edge.recommendations::jsonb->>'threshold_km', '')::double precision
               AS threshold_km,
           row_number() OVER (
               PARTITION BY anchor.anchor_place_id, restaurant.id
               ORDER BY NULLIF(
                   near_edge.recommendations::jsonb->>'distance_km', ''
               )::double precision NULLS LAST, near_edge.id
           ) AS edge_rank
    FROM unnest($2::text[]) AS anchor(anchor_place_id)
    JOIN knowledge_relationships near_edge
      ON near_edge.relationship_type = 'Special_Near'
     AND (
         near_edge.from_entity_id = anchor.anchor_place_id
         OR near_edge.to_entity_id = anchor.anchor_place_id
     )
    JOIN knowledge_entities restaurant
      ON restaurant.id = CASE
          WHEN near_edge.from_entity_id = anchor.anchor_place_id
              THEN near_edge.to_entity_id
          ELSE near_edge.from_entity_id
      END
     AND restaurant.entity_type = 'Restaurant'
), pairs AS (
    SELECT nearby.anchor_place_id,
           nearby.restaurant_id,
           nearby.restaurant_name,
           nearby.distance_km,
           nearby.threshold_km,
           food.food_item_id,
           food.food_item_name,
           food.food_priority,
           food.food_confidence,
           COALESCE(
               CASE jsonb_typeof(offer.recommendations::jsonb)
                   WHEN 'array' THEN (
                       SELECT max(NULLIF(evidence->>'confidence', '')::double precision)
                       FROM jsonb_array_elements(
                           offer.recommendations::jsonb
                       ) AS evidence
                   )
                   WHEN 'object' THEN NULLIF(
                       offer.recommendations::jsonb->>'confidence', ''
                   )::double precision
               END,
               0.70
           ) AS offer_confidence
    FROM nearby_restaurants nearby
    JOIN knowledge_relationships offer
      ON offer.from_entity_id = nearby.restaurant_id
     AND offer.relationship_type = 'Offer_Item'
    JOIN special_foods food ON food.food_item_id = offer.to_entity_id
    WHERE nearby.edge_rank = 1
      AND COALESCE(offer.recommendations::jsonb->>'status', 'verified') <> 'rejected'
)
SELECT pairs.anchor_place_id,
       pairs.restaurant_id,
       pairs.restaurant_name,
       pairs.distance_km,
       pairs.threshold_km,
       pairs.food_item_id,
       pairs.food_item_name,
       LEAST(1.0, GREATEST(
           0.0,
           CASE WHEN pairs.food_priority <= 1.0
                THEN pairs.food_priority ELSE pairs.food_priority / 100.0 END
       )) AS food_priority,
       LEAST(1.0, GREATEST(0.0, pairs.food_confidence)) AS food_confidence,
       LEAST(1.0, GREATEST(0.0, pairs.offer_confidence)) AS offer_confidence
FROM pairs
ORDER BY pairs.anchor_place_id,
         pairs.food_priority DESC,
         pairs.distance_km ASC NULLS LAST,
         pairs.restaurant_id,
         pairs.food_item_id
"""
