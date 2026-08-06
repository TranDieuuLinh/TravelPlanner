"""Add user-facing processing phase to import jobs.

Revision ID: 20260805_0042
Revises: 20260805_0041
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0042"
down_revision: str | None = "20260805_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
    op.drop_column("knowledge_graph_imports", "processing_phase")
