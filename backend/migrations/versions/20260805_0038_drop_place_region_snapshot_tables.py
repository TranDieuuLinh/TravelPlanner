"""drop persisted place region statistics snapshots

Revision ID: 20260805_0038
Revises: 20260805_0037
Create Date: 2026-08-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0038"
down_revision: str | None = "20260805_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("place_region_catalog_state")
    op.drop_table("place_region_snapshots")


def downgrade() -> None:
    op.create_table(
        "place_region_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("region_key", sa.String(160), nullable=False),
        sa.Column("catalog_version", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("place_count", sa.Integer(), nullable=False),
        sa.Column("active_place_count", sa.Integer(), nullable=False),
        sa.Column("source_max_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "region_key",
            "catalog_version",
            "algorithm_version",
            name="uq_place_region_snapshot_version",
        ),
    )
    op.create_index(
        "ix_place_region_snapshots_region_generated",
        "place_region_snapshots",
        ["region_key", "generated_at"],
    )
    op.create_index(
        "ix_place_region_snapshots_fingerprint",
        "place_region_snapshots",
        ["region_key", "source_fingerprint"],
    )
    op.create_table(
        "place_region_catalog_state",
        sa.Column("region_key", sa.String(160), primary_key=True),
        sa.Column("catalog_version", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("current_snapshot_id", sa.String(36), nullable=True),
        sa.Column("dirty_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("refresh_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["current_snapshot_id"],
            ["place_region_snapshots.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_place_region_catalog_state_refresh",
        "place_region_catalog_state",
        ["refresh_status", "next_retry_at"],
    )
