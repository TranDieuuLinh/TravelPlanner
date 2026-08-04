"""add URL itinerary guidance to user must-place

Revision ID: 20260730_0009
Revises: 20260730_0008
Create Date: 2026-07-29 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260730_0009"
down_revision: str | None = "20260730_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_must_place", sa.Column("source_order", sa.Integer(), nullable=True))
    op.add_column("user_must_place", sa.Column("source_day", sa.Integer(), nullable=True))
    op.add_column(
        "user_must_place",
        sa.Column("source_time_hint", sa.String(length=64), nullable=True),
    )
    op.add_column("user_must_place", sa.Column("source_activity", sa.Text(), nullable=True))
    op.add_column(
        "user_must_place",
        sa.Column("source_duration_minutes", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_user_must_place_source_order",
        "user_must_place",
        "source_order IS NULL OR source_order >= 1",
    )
    op.create_check_constraint(
        "ck_user_must_place_source_day",
        "user_must_place",
        "source_day IS NULL OR source_day BETWEEN 1 AND 30",
    )
    op.create_check_constraint(
        "ck_user_must_place_source_duration",
        "user_must_place",
        "source_duration_minutes IS NULL OR source_duration_minutes BETWEEN 15 AND 720",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_user_must_place_source_duration",
        "user_must_place",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_must_place_source_day",
        "user_must_place",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_must_place_source_order",
        "user_must_place",
        type_="check",
    )
    op.drop_column("user_must_place", "source_duration_minutes")
    op.drop_column("user_must_place", "source_activity")
    op.drop_column("user_must_place", "source_time_hint")
    op.drop_column("user_must_place", "source_day")
    op.drop_column("user_must_place", "source_order")
