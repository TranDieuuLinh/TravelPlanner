"""Bayesian reputation CTEs used by generic Knowledge Graph discovery."""

GENERIC_TRAVEL_RANKING_CTES = """
generic_features AS (
    SELECT entity.id,
           EXISTS (
               SELECT 1
               FROM knowledge_relationships special
               WHERE special.to_entity_id = entity.id
                 AND special.from_entity_id IN (SELECT id FROM adm_scope)
                 AND special.relationship_type = 'Special_Experience'
           ) AS is_special,
           EXISTS (
               SELECT 1
               FROM knowledge_relationships offered
               JOIN knowledge_entities activity
                 ON activity.id = offered.to_entity_id
                AND activity.entity_type = 'ActivityItem'
               WHERE offered.from_entity_id = entity.id
                 AND offered.relationship_type = 'Offer_Item'
           ) AS has_activity,
           (
               (props.latitude IS NOT NULL)::integer
               + (props.longitude IS NOT NULL)::integer
               + (
                   props.time_duration IS NOT NULL
                   OR EXISTS (
                       SELECT 1
                       FROM knowledge_relationships styled
                       JOIN knowledge_properties style_property
                         ON style_property.entity_id = styled.to_entity_id
                        AND style_property.key = 'time_duration'
                       WHERE styled.from_entity_id = entity.id
                         AND styled.relationship_type = 'Has_Style'
                   )
               )::integer
               + (
                   props.price_min IS NOT NULL
                   OR props.price_max IS NOT NULL
               )::integer
           ) AS completeness,
           NULLIF(props.rating, '')::double precision AS rating,
           NULLIF(props.review_count, '')::bigint AS review_count
    FROM scoped
    JOIN knowledge_entities entity ON entity.id = scoped.id
    LEFT JOIN LATERAL (
        SELECT
            max(property.value) FILTER (WHERE property.key = 'latitude') AS latitude,
            max(property.value) FILTER (WHERE property.key = 'longitude') AS longitude,
            max(property.value) FILTER (WHERE property.key = 'time_duration') AS time_duration,
            max(property.value) FILTER (WHERE property.key = 'price_min') AS price_min,
            max(property.value) FILTER (WHERE property.key = 'price_max') AS price_max,
            max(property.value) FILTER (WHERE property.key = 'rating') AS rating,
            max(property.value) FILTER (WHERE property.key = 'review_count') AS review_count
        FROM knowledge_properties property
        WHERE property.entity_id = entity.id
    ) props ON true
    WHERE $1 IN ('travel place', 'restaurant', 'cafe', 'entertainment', 'hotel')
      AND entity.entity_type = ANY($3::text[])
      AND props.latitude IS NOT NULL
      AND props.longitude IS NOT NULL
      AND (
          entity.entity_type = 'Accommodation'
          OR props.time_duration IS NOT NULL
          OR EXISTS (
              SELECT 1
              FROM knowledge_relationships styled
              JOIN knowledge_properties style_property
                ON style_property.entity_id = styled.to_entity_id
               AND style_property.key = 'time_duration'
              WHERE styled.from_entity_id = entity.id
                AND styled.relationship_type = 'Has_Style'
          )
      )
), generic_reputation AS (
    SELECT avg(rating) FILTER (WHERE rating IS NOT NULL) AS prior_mean,
           GREATEST(
               20.0,
               COALESCE(
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY review_count)
                       FILTER (WHERE rating IS NOT NULL AND review_count IS NOT NULL),
                   0.0
               )
           ) AS prior_weight
    FROM generic_features
), generic_bayesian AS (
    SELECT feature.*,
           CASE WHEN feature.rating IS NULL THEN NULL
                ELSE (
                    COALESCE(feature.review_count, 0) * feature.rating
                    + reputation.prior_weight * reputation.prior_mean
                ) / (COALESCE(feature.review_count, 0) + reputation.prior_weight)
           END AS bayesian_rating,
           COALESCE(feature.review_count, 0)::double precision
               / (COALESCE(feature.review_count, 0) + reputation.prior_weight)
               AS review_reliability
    FROM generic_features feature
    CROSS JOIN generic_reputation reputation
), generic_travel_ranked AS (
    SELECT scored.id,
           scored.bayesian_rating,
           scored.bayesian_quality,
           row_number() OVER (
               PARTITION BY scored.is_special
               ORDER BY scored.has_activity DESC,
                        scored.completeness DESC,
                        scored.bayesian_quality DESC NULLS LAST,
                        scored.bayesian_rating DESC NULLS LAST,
                        scored.review_count DESC NULLS LAST,
                        scored.id
           ) AS discovery_rank
    FROM (
        SELECT candidate.*,
               candidate.bayesian_rating / 5.0
                   * (0.70 + 0.30 * candidate.review_reliability)
                   AS bayesian_quality
        FROM generic_bayesian candidate
    ) scored
)
""".strip()
