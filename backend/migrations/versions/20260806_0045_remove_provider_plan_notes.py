"""remove provider metadata from plan note sources

Revision ID: 20260806_0045
Revises: 20260806_0044
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op


revision: str = "20260806_0045"
down_revision: str | None = "20260806_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CREATE_STRIP_FUNCTION = r"""
CREATE FUNCTION pg_temp.vsf_strip_provider_plan_notes(payload jsonb)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN jsonb_typeof(payload->'days') <> 'array' THEN payload
        ELSE jsonb_set(
            payload,
            '{days}',
            COALESCE(
                (
                    SELECT jsonb_agg(
                        CASE
                            WHEN jsonb_typeof(day->'items') <> 'array' THEN day
                            ELSE jsonb_set(
                                day,
                                '{items}',
                                COALESCE(
                                    (
                                        SELECT jsonb_agg(
                                            CASE
                                                WHEN jsonb_typeof(item->'noteSources') <> 'array'
                                                    THEN item
                                                ELSE jsonb_set(
                                                    item,
                                                    '{noteSources}',
                                                    COALESCE(
                                                        (
                                                            SELECT jsonb_agg(source_note)
                                                            FROM jsonb_array_elements(
                                                                item->'noteSources'
                                                            ) AS source_note
                                                            WHERE source_note->>'type' NOT IN (
                                                                'google_maps',
                                                                'place_provider'
                                                            )
                                                        ),
                                                        '[]'::jsonb
                                                    )
                                                )
                                            END
                                        )
                                        FROM jsonb_array_elements(day->'items') AS item
                                    ),
                                    '[]'::jsonb
                                )
                            )
                        END
                    )
                    FROM jsonb_array_elements(payload->'days') AS day
                ),
                '[]'::jsonb
            )
        )
    END
$$
"""


def upgrade() -> None:
    op.execute(_CREATE_STRIP_FUNCTION)
    op.execute(
        """
        UPDATE trip_chats
        SET current_plan = pg_temp.vsf_strip_provider_plan_notes(current_plan::jsonb)::json
        WHERE current_plan IS NOT NULL
          AND (
              current_plan::text LIKE '%\"type\": \"place_provider\"%'
              OR current_plan::text LIKE '%\"type\": \"google_maps\"%'
          )
        """
    )
    op.execute(
        """
        UPDATE trip_revisions
        SET plan_payload = pg_temp.vsf_strip_provider_plan_notes(plan_payload::jsonb)::json
        WHERE plan_payload IS NOT NULL
          AND (
              plan_payload::text LIKE '%\"type\": \"place_provider\"%'
              OR plan_payload::text LIKE '%\"type\": \"google_maps\"%'
          )
        """
    )
    op.execute(
        """
        UPDATE marketplace_plan_versions
        SET preview_snapshot = pg_temp.vsf_strip_provider_plan_notes(
            preview_snapshot::jsonb
        )::json
        WHERE preview_snapshot IS NOT NULL
          AND (
              preview_snapshot::text LIKE '%\"type\": \"place_provider\"%'
              OR preview_snapshot::text LIKE '%\"type\": \"google_maps\"%'
          )
        """
    )


def downgrade() -> None:
    # Removed prose was derived from structured provider fields and must not be
    # recreated. Address, rating, hours and provider identity remain intact.
    pass
