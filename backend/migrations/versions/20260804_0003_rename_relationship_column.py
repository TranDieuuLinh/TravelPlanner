"""rename relationship column to relationship_type

Revision ID: 20260804_0003
Revises: 20260804_0002
Create Date: 2026-08-04 11:22:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260804_0003"
down_revision: str | Sequence[str] | None = "20260804_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE knowledge_relationships
        RENAME COLUMN relationship TO relationship_type
    """)
    op.execute("""
        ALTER TABLE knowledge_graph_import_edges
        RENAME COLUMN relationship TO relationship_type
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE knowledge_relationships
        RENAME COLUMN relationship_type TO relationship
    """)
    op.execute("""
        ALTER TABLE knowledge_graph_import_edges
        RENAME COLUMN relationship_type TO relationship
    """)
