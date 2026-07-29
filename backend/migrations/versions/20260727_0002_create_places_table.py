"""create places table

Revision ID: 20260727_0002
Revises: 20260727_0003_market
Create Date: 2026-07-27 17:00:00
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260727_0002"
down_revision: str | None = "20260727_0003_market"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("place_type", sa.String(length=64), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("city", sa.String(length=160), nullable=True),
        sa.Column("country", sa.String(length=160), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region_key", sa.String(length=160), nullable=False),
        sa.Column("primary_area", sa.String(length=160), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="unverified",
        ),
        sa.Column("opening_hours", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("typical_duration_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "data_confidence",
            sa.String(length=16),
            nullable=False,
            server_default="low",
        ),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revision",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('active', 'temporarily_closed', 'permanently_closed', 'unverified')",
            name="ck_places_status",
        ),
        sa.CheckConstraint(
            "data_confidence IN ('low', 'medium', 'high')",
            name="ck_places_data_confidence",
        ),
        sa.CheckConstraint(
            "typical_duration_minutes IS NULL OR typical_duration_minutes > 0",
            name="ck_places_positive_duration",
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="ck_places_latitude",
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="ck_places_longitude",
        ),
    )
    op.create_index(
        "ix_places_region_status",
        "places",
        ["region_key", "status"],
    )
    op.create_index(
        "ix_places_region_type_status",
        "places",
        ["region_key", "place_type", "status"],
    )
    op.create_index(
        "ix_places_source_fetched_at",
        "places",
        ["source_fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_places_source_fetched_at", table_name="places")
    op.drop_index("ix_places_region_type_status", table_name="places")
    op.drop_index("ix_places_region_status", table_name="places")
    op.drop_table("places")
