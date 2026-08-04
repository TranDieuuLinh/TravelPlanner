"""isolate Explorer place persistence in user_must_place

Revision ID: 20260728_0005
Revises: 20260728_0004
Create Date: 2026-07-28 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op

revision: str = "20260728_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())
    must_place_columns = (
        {
            column["name"]
            for column in inspector.get_columns("user_must_place")
        }
        if "user_must_place" in table_names
        else set()
    )

    # Databases that ran the original 0004 still reference travel_intakes and
    # places. Move those rows into the standalone schema without writing back
    # to places. Fresh databases already have the standalone 0004 schema.
    if "place_id" in must_place_columns:
        _create_replacement_table()
        op.execute(
            sa.text(
                """
                INSERT INTO user_must_place_v2 (
                    id, intake_id, user_id, destination, candidate_key,
                    candidate_name, category, address_hint, resolved_name,
                    address, city, country, country_code, primary_area,
                    latitude, longitude, description, provider, external_id,
                    sources, confidence, notes, data_confidence, fetched_at,
                    attribution, resolution_status, created_at, updated_at
                )
                SELECT
                    ump.id, ump.intake_id, ti.user_id, ti.destination,
                    ump.candidate_key, ump.candidate_name, ump.category,
                    ump.address_hint, COALESCE(p.name, ump.candidate_name),
                    p.address, p.city, p.country, p.country_code,
                    p.primary_area, p.latitude, p.longitude, p.description,
                    NULL, NULL, ump.sources, ump.confidence, ump.notes,
                    COALESCE(p.data_confidence, 'low'), p.source_fetched_at,
                    NULL, ump.resolution_status, ump.created_at, ump.updated_at
                FROM user_must_place AS ump
                JOIN travel_intakes AS ti ON ti.id = ump.intake_id
                LEFT JOIN places AS p ON p.id = ump.place_id
                """
            )
        )
        op.drop_table("user_must_place")
        op.rename_table("user_must_place_v2", "user_must_place")
        op.create_index(
            "ix_user_must_place_intake",
            "user_must_place",
            ["intake_id"],
        )

    inspector = sa.inspect(connection)
    table_names = set(inspector.get_table_names())
    if "travel_intakes" in table_names:
        op.drop_table("travel_intakes")

    place_columns = {
        column["name"] for column in inspector.get_columns("places")
    }
    if "description" in place_columns:
        op.drop_column("places", "description")


def downgrade() -> None:
    # Revision 0004 now defines the standalone schema too. This corrective
    # migration is intentionally a no-op on downgrade.
    pass


def _create_replacement_table() -> None:
    op.create_table(
        "user_must_place_v2",
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
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "confidence",
            sa.Numeric(4, 3),
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
            name="ck_user_must_place_v2_confidence",
        ),
        sa.CheckConstraint(
            "resolution_status IN ('resolved', 'provisional', 'unresolved')",
            name="ck_user_must_place_v2_resolution_status",
        ),
        sa.CheckConstraint(
            "data_confidence IN ('low', 'medium', 'high')",
            name="ck_user_must_place_v2_data_confidence",
        ),
        sa.UniqueConstraint(
            "intake_id",
            "candidate_key",
            name="uq_user_must_place_v2_intake_candidate",
        ),
    )
