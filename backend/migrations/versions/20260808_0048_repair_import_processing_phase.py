"""Repair the import processing phase column when a database was stamped ahead.

Some development databases recorded the migration revision without applying
the column change. Keep the migration idempotent so those databases converge
without affecting already-correct schemas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260808_0048"
down_revision: str | None = "20260807_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("knowledge_graph_imports")}
    if "processing_phase" not in columns:
        op.add_column(
            "knowledge_graph_imports",
            sa.Column(
                "processing_phase",
                sa.String(length=32),
                nullable=False,
                server_default="queued",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("knowledge_graph_imports")}
    if "processing_phase" in columns:
        op.drop_column("knowledge_graph_imports", "processing_phase")
