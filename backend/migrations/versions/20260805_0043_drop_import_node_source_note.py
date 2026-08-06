"""Drop the deprecated import-node display note.

Revision ID: 20260805_0043
Revises: 20260805_0042
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0043"
down_revision: str | None = "20260805_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("knowledge_graph_import_nodes", "source_note")


def downgrade() -> None:
    op.add_column(
        "knowledge_graph_import_nodes",
        sa.Column("source_note", sa.Text(), nullable=True),
    )
