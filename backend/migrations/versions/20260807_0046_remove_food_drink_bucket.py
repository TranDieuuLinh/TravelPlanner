"""split legacy food_drink data into canonical ontology types

Revision ID: 20260807_0046
Revises: 20260806_0045
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260807_0046"
down_revision: str | None = "20260806_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CREATE_PLAN_BACKFILL_FUNCTION = r"""
CREATE FUNCTION pg_temp.travelplanner_split_food_bucket(payload jsonb)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN jsonb_typeof(payload->'days') <> 'array' THEN payload
        ELSE jsonb_set(
            payload,
            '{days}',
            COALESCE((
                SELECT jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(day->'items') <> 'array' THEN day
                        ELSE jsonb_set(
                            day,
                            '{items}',
                            COALESCE((
                                SELECT jsonb_agg(
                                    CASE
                                        WHEN item::text NOT LIKE '%food_drink%'
                                             AND lower(COALESCE(item->>'ontologyType', ''))
                                                 NOT IN ('food', 'restaurant', 'drink_dessert', 'drinkdessert', 'cafe')
                                             AND lower(COALESCE(item->>'timelineCategory', '')) <> 'food'
                                             AND lower(COALESCE(item->>'category', '')) <> 'food'
                                            THEN item
                                        ELSE jsonb_set(
                                            jsonb_set(
                                                item,
                                                '{tags}',
                                                COALESCE((
                                                    SELECT jsonb_agg(DISTINCT tag)
                                                    FROM (
                                                        SELECT CASE
                                                            WHEN value = 'food_drink'
                                                                THEN 'food'
                                                            ELSE value
                                                        END AS tag
                                                        FROM jsonb_array_elements_text(
                                                            COALESCE(item->'tags', '[]'::jsonb)
                                                        )
                                                    ) normalized_tags
                                                ), '[]'::jsonb)
                                            ),
                                            '{ontologyType}',
                                            to_jsonb(
                                                CASE
                                                    WHEN item->>'ontologyType' IN ('Restaurant', 'DrinkDessert')
                                                        THEN item->>'ontologyType'
                                                    WHEN lower(concat_ws(' ',
                                                        item->>'role',
                                                        item->>'sourceActivity'
                                                    )) ~ '(breakfast|lunch|dinner|meal)'
                                                        THEN 'Restaurant'
                                                    WHEN lower(concat_ws(' ',
                                                        item->>'name',
                                                        item->>'placeType',
                                                        item->>'sourceActivity'
                                                    )) ~ '(cafe|coffee|bakery|cake|dessert|ice[ _-]?cream|gelato|bingsu|chè|che|tea|juice|snack)'
                                                        THEN 'DrinkDessert'
                                                    ELSE 'Restaurant'
                                                END
                                            ),
                                            true
                                        )
                                    END
                                )
                                FROM jsonb_array_elements(day->'items') AS item
                            ), '[]'::jsonb)
                        )
                    END
                )
                FROM jsonb_array_elements(payload->'days') AS day
            ), '[]'::jsonb)
        )
    END
$$
"""


def upgrade() -> None:
    op.execute(
        r"""
        WITH evidence AS (
            SELECT
                ke.id,
                lower(concat_ws(' ',
                    ke.canonical_name,
                    string_agg(kp.value, ' ' ORDER BY kp.key)
                )) AS text
            FROM knowledge_entities ke
            LEFT JOIN knowledge_properties kp
              ON kp.entity_id = ke.id
             AND kp.key IN ('place_type', 'place_category', 'source_category', 'metadata')
            WHERE lower(ke.entity_type) IN (
                'food_drink', 'food', 'restaurant', 'drink_dessert', 'drinkdessert', 'cafe'
            )
            GROUP BY ke.id, ke.canonical_name
        )
        UPDATE knowledge_entities ke
        SET entity_type = CASE
            WHEN evidence.text ~ '(cafe|coffee|bakery|cake|dessert|ice[ _-]?cream|gelato|bingsu|chè|che|tea|juice|snack)'
                THEN 'DrinkDessert'
            ELSE 'Restaurant'
        END,
        updated_at = now()
        FROM evidence
        WHERE ke.id = evidence.id
        """
    )
    op.execute(
        """
        UPDATE knowledge_properties kp
        SET value = ke.entity_type,
            updated_at = now()
        FROM knowledge_entities ke
        WHERE kp.entity_id = ke.id
          AND kp.key IN ('place_group', 'place_category')
          AND lower(kp.value) = 'food_drink'
        """
    )
    op.execute(
        """
        UPDATE knowledge_properties kp
        SET value = replace(kp.value, 'food_drink', ke.entity_type),
            updated_at = now()
        FROM knowledge_entities ke
        WHERE kp.entity_id = ke.id
          AND kp.key = 'metadata'
          AND kp.value LIKE '%food_drink%'
        """
    )

    op.execute(_CREATE_PLAN_BACKFILL_FUNCTION)
    for table, column in (
        ("trip_chats", "current_plan"),
        ("trip_revisions", "plan_payload"),
        ("marketplace_plan_versions", "preview_snapshot"),
    ):
        op.execute(
            f"""
            UPDATE {table}
            SET {column} = pg_temp.travelplanner_split_food_bucket(
                {column}::jsonb
            )::json
            WHERE {column} IS NOT NULL
            """
        )


def downgrade() -> None:
    raise RuntimeError(
        "Restaurant/DrinkDessert cannot be safely merged back into food_drink"
    )
