"""Backfill Knowledge Graph ownership for reviews/images/visited places.

Revision ID: 20260805_0039
Revises: 20260805_0038
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0039"
down_revision: str | None = "20260805_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the legacy place_id columns during this migration.  A few runtime
    # readers still use them; the nullable entity_id columns allow an
    # application cutover and rollback without losing rows.
    op.add_column(
        "reviews",
        sa.Column("entity_id", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "place_images",
        sa.Column("entity_id", sa.String(length=96), nullable=True),
    )
    op.add_column(
        "user_visited_places",
        sa.Column("entity_id", sa.String(length=96), nullable=True),
    )

    op.create_index("ix_reviews_entity_id", "reviews", ["entity_id"])
    op.create_index("ix_place_images_entity_id", "place_images", ["entity_id"])
    op.create_index(
        "ix_user_visited_places_entity_id",
        "user_visited_places",
        ["entity_id"],
    )
    op.create_foreign_key(
        "fk_reviews_knowledge_entity",
        "reviews",
        "knowledge_entities",
        ["entity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_place_images_knowledge_entity",
        "place_images",
        "knowledge_entities",
        ["entity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_user_visited_places_knowledge_entity",
        "user_visited_places",
        "knowledge_entities",
        ["entity_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    bind = op.get_bind()
    # The current catalog and graph use different IDs.  The imported
    # canonical Google Maps URL is the stable, exact crosswalk; deliberately
    # do not fuzzy-match names or coordinates here.
    mapping_sql = sa.text(
        """
        CREATE TEMP TABLE _place_entity_map ON COMMIT DROP AS
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
    bind.execute(mapping_sql)
    bind.execute(
        sa.text(
            """
            UPDATE reviews r
            SET entity_id = m.entity_id
            FROM _place_entity_map m
            WHERE r.place_id = m.place_id
              AND r.entity_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE place_images i
            SET entity_id = m.entity_id
            FROM _place_entity_map m
            WHERE i.place_id = m.place_id
              AND i.entity_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE user_visited_places v
            SET entity_id = m.entity_id
            FROM _place_entity_map m
            WHERE v.place_id = m.place_id
              AND v.entity_id IS NULL
            """
        )
    )

    # Opening hours become a canonical KG property.  Preserve the structured
    # JSON shape already used by Place and keep the source URL as provenance.
    bind.execute(
        sa.text(
            """
            INSERT INTO knowledge_properties (entity_id, key, value, source, note, updated_at)
            SELECT m.entity_id,
                   'opening_hours',
                   p.opening_hours::text,
                   p.source_link,
                   'Backfilled from places.opening_hours; source freshness is the Place snapshot time.',
                   COALESCE(p.source_fetched_at, now())
            FROM _place_entity_map m
            JOIN places p ON p.id = m.place_id
            WHERE p.opening_hours IS NOT NULL
              AND jsonb_typeof(p.opening_hours::jsonb) = 'array'
              AND jsonb_array_length(p.opening_hours::jsonb) > 0
            ON CONFLICT (entity_id, key) DO UPDATE
            SET value = EXCLUDED.value,
                source = EXCLUDED.source,
                note = EXCLUDED.note,
                updated_at = EXCLUDED.updated_at
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM knowledge_properties
            WHERE key = 'opening_hours'
              AND note = 'Backfilled from places.opening_hours; source freshness is the Place snapshot time.'
            """
        )
    )
    op.drop_constraint(
        "fk_user_visited_places_knowledge_entity",
        "user_visited_places",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_place_images_knowledge_entity",
        "place_images",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_reviews_knowledge_entity",
        "reviews",
        type_="foreignkey",
    )
    op.drop_index("ix_user_visited_places_entity_id", table_name="user_visited_places")
    op.drop_index("ix_place_images_entity_id", table_name="place_images")
    op.drop_index("ix_reviews_entity_id", table_name="reviews")
    op.drop_column("user_visited_places", "entity_id")
    op.drop_column("place_images", "entity_id")
    op.drop_column("reviews", "entity_id")
