"""remove unsupported route sources from persisted trip plans

Revision ID: 20260801_0017
Revises: 20260801_0016
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260801_0017"
down_revision: str | None = "20260801_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CLEAN_PLAN_SQL = """
CREATE OR REPLACE FUNCTION travelplanner_remove_unsupported_transport_routes(payload jsonb)
RETURNS jsonb
LANGUAGE sql
AS $$
    SELECT CASE
        WHEN payload IS NULL OR jsonb_typeof(payload->'days') <> 'array'
            THEN payload
        ELSE jsonb_set(
            payload,
            '{days}',
            COALESCE(
                (
                    SELECT jsonb_agg(
                        jsonb_set(
                            day_value,
                            '{transportLegs}',
                            COALESCE(
                                (
                                    SELECT jsonb_agg(
                                        jsonb_set(
                                            leg_value,
                                            '{alternatives}',
                                            COALESCE(
                                                (
                                                    SELECT jsonb_agg(
                                                        alternative_value
                                                        ORDER BY alternative_order
                                                    )
                                                    FROM jsonb_array_elements(
                                                        COALESCE(
                                                            leg_value->'alternatives',
                                                            '[]'::jsonb
                                                        )
                                                    ) WITH ORDINALITY AS alternatives(
                                                        alternative_value,
                                                        alternative_order
                                                    )
                                                    WHERE alternative_value->>'source' IN (
                                                        'valhalla_routing',
                                                        'opentripplanner_transit',
                                                        'geodesic_estimate'
                                                    )
                                                ),
                                                '[]'::jsonb
                                            ),
                                            true
                                        )
                                        ORDER BY leg_order
                                    )
                                    FROM jsonb_array_elements(
                                        COALESCE(
                                            day_value->'transportLegs',
                                            '[]'::jsonb
                                        )
                                    ) WITH ORDINALITY AS legs(leg_value, leg_order)
                                    WHERE leg_value->>'source' IN (
                                        'valhalla_routing',
                                        'opentripplanner_transit',
                                        'geodesic_estimate'
                                    )
                                ),
                                '[]'::jsonb
                            ),
                            true
                        )
                        ORDER BY day_order
                    )
                    FROM jsonb_array_elements(payload->'days')
                        WITH ORDINALITY AS days(day_value, day_order)
                ),
                '[]'::jsonb
            ),
            true
        )
    END
$$;
"""


def upgrade() -> None:
    op.execute(_CLEAN_PLAN_SQL)
    op.execute(
        """
        UPDATE trip_chats
        SET current_plan = travelplanner_remove_unsupported_transport_routes(
            current_plan::jsonb
        )::json
        WHERE current_plan IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE trip_chat_plan_revisions
        SET plan_payload = travelplanner_remove_unsupported_transport_routes(
            plan_payload::jsonb
        )::json
        """
    )
    op.execute("DROP FUNCTION travelplanner_remove_unsupported_transport_routes(jsonb)")


def downgrade() -> None:
    # Removed third-party route payloads cannot be reconstructed safely.
    pass
