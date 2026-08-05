"""Detach retained data and drop the legacy place catalog.

Revision ID: 20260805_0041
Revises: 20260805_0040
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0041"
down_revision: str | None = "20260805_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    for table in ("reviews", "place_images", "user_visited_places"):
        missing = bind.scalar(
            sa.text(f"SELECT count(*) FROM {table} WHERE entity_id IS NULL")
        )
        if missing:
            raise RuntimeError(
                f"Cannot drop places: {table} still has {missing} unmapped rows"
            )

    op.drop_constraint(
        "fk_place_images_knowledge_entity", "place_images", type_="foreignkey"
    )
    op.alter_column(
        "place_images",
        "entity_id",
        existing_type=sa.String(length=96),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_place_images_knowledge_entity",
        "place_images",
        "knowledge_entities",
        ["entity_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_place_images_place_url", "place_images", type_="unique")
    op.create_unique_constraint(
        "uq_knowledge_entity_images_entity_url",
        "place_images",
        ["entity_id", "image_url"],
    )
    op.drop_constraint(
        "place_images_place_id_fkey", "place_images", type_="foreignkey"
    )
    op.drop_index("ix_place_images_place_id", table_name="place_images")
    op.drop_column("place_images", "place_id")
    op.rename_table("place_images", "knowledge_entity_images")
    op.execute(
        "ALTER INDEX ix_place_images_entity_id RENAME TO ix_knowledge_entity_images_entity_id"
    )

    op.drop_constraint(
        "fk_reviews_knowledge_entity", "reviews", type_="foreignkey"
    )
    op.alter_column(
        "reviews",
        "entity_id",
        existing_type=sa.String(length=96),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_reviews_knowledge_entity",
        "reviews",
        "knowledge_entities",
        ["entity_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("reviews_place_id_fkey", "reviews", type_="foreignkey")
    op.drop_index("ix_reviews_place_id", table_name="reviews")
    op.drop_column("reviews", "place_id")

    op.drop_constraint(
        "user_visited_places_place_id_fkey",
        "user_visited_places",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_user_visited_places_place_id", table_name="user_visited_places"
    )
    op.drop_column("user_visited_places", "place_id")

    # Amenities were explicitly left out of the MVP cutover. Opening hours are
    # already preserved as structured knowledge_properties.
    op.drop_table("place_amenities")
    op.drop_table("place_opening_hours")
    op.drop_table("places")


def downgrade() -> None:
    raise RuntimeError(
        "The legacy place catalog cannot be reconstructed by downgrade; restore a database backup instead."
    )
