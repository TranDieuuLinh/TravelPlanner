"""Create festivals table for Vietnamese festival data.

Revision ID: 20260731_0001
Revises: 20260730_0014
Create Date: 2026-07-31

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260731_0001"
down_revision = "20260730_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "festivals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(64), nullable=False, index=True),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("venue", sa.String(512), nullable=True),
        sa.Column("scale_level", sa.String(32), nullable=False, server_default="dia-phuong"),
        sa.Column("timing", sa.String(255), nullable=True),
        sa.Column("province", sa.String(160), nullable=True),
        sa.Column("district", sa.String(160), nullable=True),
        sa.Column("deity", sa.Text, nullable=True),
        sa.Column("ceremony_part", sa.Text, nullable=True),
        sa.Column("festival_part", sa.Text, nullable=True),
        sa.Column("festival_type", sa.String(64), nullable=True),
        sa.Column("documentation", sa.Text, nullable=True),
        sa.Column("protection_measure", sa.Text, nullable=True),
        sa.Column("registration_time", sa.String(255), nullable=True),
        sa.Column("recurrence", sa.String(64), nullable=True),
        sa.Column("listed_year", sa.Integer, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_unique_constraint(
        "uq_festival_source_id",
        "festivals",
        ["source_id"],
    )

    # Indexes for common queries
    op.create_index("ix_festivals_province", "festivals", ["province"])
    op.create_index("ix_festivals_scale_level", "festivals", ["scale_level"])
    op.create_index("ix_festivals_timing", "festivals", ["timing"])


def downgrade() -> None:
    op.drop_index("ix_festivals_timing", table_name="festivals")
    op.drop_index("ix_festivals_scale_level", table_name="festivals")
    op.drop_index("ix_festivals_province", table_name="festivals")
    op.drop_constraint("uq_festival_source_id", "festivals", type_="unique")
    op.drop_table("festivals")
