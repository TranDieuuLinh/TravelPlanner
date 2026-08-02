"""add pgvector embeddings to places

Revision ID: 20260801_0004
Revises: 20260731_0003
Create Date: 2026-08-01 13:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector


revision: str = "20260801_0004"
down_revision: str | None = "20260731_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.add_column("places", sa.Column("embedding", Vector(768), nullable=True))
    op.add_column(
        "places", sa.Column("embedding_model", sa.String(length=96), nullable=True)
    )
    op.add_column(
        "places",
        sa.Column("embedding_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "places", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_places_embedding_hnsw_cosine",
        "places",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_places_embedding_model",
        "places",
        ["embedding_model"],
    )


def downgrade() -> None:
    op.drop_index("ix_places_embedding_model", table_name="places")
    op.drop_index("ix_places_embedding_hnsw_cosine", table_name="places")
    op.drop_column("places", "embedded_at")
    op.drop_column("places", "embedding_content_hash")
    op.drop_column("places", "embedding_model")
    op.drop_column("places", "embedding")
