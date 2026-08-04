"""create user must-place intake table

Revision ID: 20260728_0004
Revises: 20260727_0003
Create Date: 2026-07-28 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0004"
down_revision: str | None = "20260727_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_must_place",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("intake_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("candidate_key", sa.String(length=255), nullable=False),
        sa.Column("candidate_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("address_hint", sa.Text(), nullable=True),
        sa.Column("resolved_name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("country", sa.String(length=255), nullable=True),
        sa.Column("country_code", sa.String(length=8), nullable=True),
        sa.Column("primary_area", sa.String(length=255), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "confidence",
            sa.Numeric(precision=4, scale=3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "data_confidence",
            sa.String(length=16),
            nullable=False,
            server_default="low",
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column(
            "resolution_status",
            sa.String(length=24),
            nullable=False,
            server_default="unresolved",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1",
            name="ck_user_must_place_confidence",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('resolved', 'provisional', 'unresolved')",
            name="ck_user_must_place_resolution_status",
        ),
        sa.CheckConstraint(
            "data_confidence IN ('low', 'medium', 'high')",
            name="ck_user_must_place_data_confidence",
        ),
        sa.UniqueConstraint(
            "intake_id",
            "candidate_key",
            name="uq_user_must_place_intake_candidate",
        ),
    )
    op.create_index(
        "ix_user_must_place_intake_user",
        "user_must_place",
        ["intake_id", "user_id"],
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_must_place_intake_user")
    op.execute("DROP INDEX IF EXISTS ix_user_must_place_intake")
    op.drop_table("user_must_place")
