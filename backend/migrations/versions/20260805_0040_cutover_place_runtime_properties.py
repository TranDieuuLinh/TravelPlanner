"""Backfill Planner KG properties and switch visited-place identity.

Revision ID: 20260805_0040
Revises: 20260805_0039
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0040"
down_revision: str | None = "20260805_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            CREATE TEMP TABLE _place_entity_map_runtime ON COMMIT DROP AS
            SELECT p.id AS place_id, min(kp.entity_id) AS entity_id
            FROM places p
            JOIN knowledge_properties kp
              ON kp.key = 'source_url'
             AND kp.value = p.source_link
            WHERE p.source_link IS NOT NULL
            GROUP BY p.id
            HAVING count(DISTINCT kp.entity_id) = 1
            """
        )
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO knowledge_properties
                (entity_id, key, value, source, note, updated_at)
            SELECT m.entity_id,
                   values_to_copy.key,
                   values_to_copy.value,
                   p.source_link,
                   'Backfilled for KG-only Planner runtime from the legacy place snapshot.',
                   COALESCE(p.source_fetched_at, p.updated_at, now())
            FROM _place_entity_map_runtime m
            JOIN places p ON p.id = m.place_id
            CROSS JOIN LATERAL (
                VALUES
                    ('region_key', p.region_key::text),
                    ('place_type', p.place_type::text),
                    ('city', p.city::text),
                    ('country', p.country::text),
                    ('country_code', p.country_code::text),
                    ('primary_area', p.primary_area::text),
                    ('catalog_status', p.status::text),
                    ('data_confidence', p.data_confidence::text),
                    ('plus_code', p.plus_code::text),
                    ('typical_duration_minutes', p.typical_duration_minutes::text),
                    ('source_fetched_at', p.source_fetched_at::text),
                    ('revision', p.revision::text),
                    ('metadata', p.metadata::text)
            ) AS values_to_copy(key, value)
            WHERE values_to_copy.value IS NOT NULL
              AND btrim(values_to_copy.value) <> ''
            ON CONFLICT (entity_id, key) DO UPDATE
            SET value = EXCLUDED.value,
                source = EXCLUDED.source,
                note = EXCLUDED.note,
                updated_at = EXCLUDED.updated_at
            """
        )
    )

    unmapped_visits = bind.scalar(
        sa.text(
            "SELECT count(*) FROM user_visited_places WHERE entity_id IS NULL"
        )
    )
    if unmapped_visits:
        raise RuntimeError(
            "Cannot cut over user_visited_places: some rows have no exact KG entity mapping"
        )

    op.drop_constraint(
        "uq_user_visited_places_user_place",
        "user_visited_places",
        type_="unique",
    )
    op.alter_column(
        "user_visited_places",
        "place_id",
        existing_type=sa.String(length=96),
        nullable=True,
    )
    op.alter_column(
        "user_visited_places",
        "entity_id",
        existing_type=sa.String(length=96),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_user_visited_places_user_entity",
        "user_visited_places",
        ["user_id", "entity_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    missing_legacy_ids = bind.scalar(
        sa.text(
            "SELECT count(*) FROM user_visited_places WHERE place_id IS NULL"
        )
    )
    if missing_legacy_ids:
        raise RuntimeError(
            "Cannot restore required place_id after KG-only visited-place writes"
        )
    op.drop_constraint(
        "uq_user_visited_places_user_entity",
        "user_visited_places",
        type_="unique",
    )
    op.alter_column(
        "user_visited_places",
        "entity_id",
        existing_type=sa.String(length=96),
        nullable=True,
    )
    op.alter_column(
        "user_visited_places",
        "place_id",
        existing_type=sa.String(length=96),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_user_visited_places_user_place",
        "user_visited_places",
        ["user_id", "place_id"],
    )
    bind.execute(
        sa.text(
            """
            DELETE FROM knowledge_properties
            WHERE note = 'Backfilled for KG-only Planner runtime from the legacy place snapshot.'
            """
        )
    )
