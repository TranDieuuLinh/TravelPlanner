"""create place region statistics tables

Revision ID: 20260727_0003
Revises: 20260727_0002
Create Date: 2026-07-27 17:30:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260727_0003"
down_revision: str | None = "20260727_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "place_region_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("region_key", sa.String(length=160), nullable=False),
        sa.Column("catalog_version", sa.BigInteger(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("place_count", sa.Integer(), nullable=False),
        sa.Column("active_place_count", sa.Integer(), nullable=False),
        sa.Column("source_max_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "place_count >= 0 AND active_place_count >= 0 AND active_place_count <= place_count",
            name="ck_place_region_snapshot_counts",
        ),
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
        ["source_fingerprint"],
    )

    op.create_table(
        "place_region_catalog_state",
        sa.Column("region_key", sa.String(length=160), primary_key=True),
        sa.Column(
            "catalog_version",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "current_snapshot_id",
            sa.String(length=36),
            sa.ForeignKey(
                "place_region_snapshots.id",
                ondelete="SET NULL",
                name="fk_place_region_state_current_snapshot",
            ),
            nullable=True,
        ),
        sa.Column("dirty_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "refresh_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "refresh_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "refresh_status IN ('clean', 'pending', 'running', 'failed')",
            name="ck_place_region_catalog_refresh_status",
        ),
        sa.CheckConstraint(
            "catalog_version >= 0 AND refresh_attempts >= 0",
            name="ck_place_region_catalog_nonnegative",
        ),
    )
    op.create_index(
        "ix_place_region_catalog_refresh",
        "place_region_catalog_state",
        ["refresh_status", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_place_region_catalog_refresh",
        table_name="place_region_catalog_state",
    )
    op.drop_table("place_region_catalog_state")
    op.drop_index(
        "ix_place_region_snapshots_fingerprint",
        table_name="place_region_snapshots",
    )
    op.drop_index(
        "ix_place_region_snapshots_region_generated",
        table_name="place_region_snapshots",
    )
    op.drop_table("place_region_snapshots")
