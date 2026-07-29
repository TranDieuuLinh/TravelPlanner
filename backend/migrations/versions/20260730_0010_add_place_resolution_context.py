"""add place resolution context and evidence

Revision ID: 20260730_0010
Revises: 20260730_0009
Create Date: 2026-07-30 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260730_0010"
down_revision: str | None = "20260730_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_must_place",
        sa.Column("search_region", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "user_must_place",
        sa.Column(
            "source_evidence",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "user_must_place",
        sa.Column("resolution_reason", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_must_place", "resolution_reason")
    op.drop_column("user_must_place", "source_evidence")
    op.drop_column("user_must_place", "search_region")
