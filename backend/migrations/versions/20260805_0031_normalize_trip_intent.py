"""replace JSON trip intent snapshots with normalized versioned records

Revision ID: 20260805_0031
Revises: 20260804_0030
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0031"
down_revision: str | None = "20260804_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "explorer_intakes",
        sa.Column(
            "candidate_reviews",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.alter_column("explorer_intakes", "candidate_reviews", server_default=None)

    op.create_table(
        "trip_intent_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("chat_id", sa.String(length=36), nullable=False),
        sa.Column("intake_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.String(length=10), nullable=True),
        sa.Column("end_date", sa.String(length=10), nullable=True),
        sa.Column("date_flexibility", sa.String(length=16), nullable=False),
        sa.Column("party_type", sa.String(length=16), nullable=False),
        sa.Column("adults", sa.Integer(), nullable=False),
        sa.Column("children", sa.Integer(), nullable=False),
        sa.Column("infants", sa.Integer(), nullable=False),
        sa.Column("pets", sa.Integer(), nullable=False),
        sa.Column("rooms", sa.Integer(), nullable=False),
        sa.Column("budget_amount", sa.Numeric(16, 0), nullable=True),
        sa.Column("budget_currency", sa.String(length=3), nullable=False),
        sa.Column("budget_level", sa.String(length=16), nullable=False),
        sa.Column("travel_style", sa.String(length=64), nullable=False),
        sa.Column("pace", sa.String(length=16), nullable=False),
        sa.Column("accommodation_required", sa.Boolean(), nullable=False),
        sa.Column("hotel_area", sa.String(length=255), nullable=True),
        sa.Column("check_in_date", sa.String(length=10), nullable=True),
        sa.Column("check_out_date", sa.String(length=10), nullable=True),
        sa.Column("transport_required", sa.Boolean(), nullable=False),
        sa.Column("include_between_places", sa.Boolean(), nullable=False),
        sa.Column("include_arrival_departure", sa.Boolean(), nullable=False),
        sa.Column("geographic_scope", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["chat_id"], ["trip_chats.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["intake_id"], ["explorer_intakes.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "chat_id", "revision", name="uq_trip_intent_chat_revision"
        ),
    )
    op.create_index(
        "ix_trip_intent_chat_revision",
        "trip_intent_versions",
        ["chat_id", "revision"],
    )
    op.create_table(
        "trip_intent_values",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_intent_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('note','interest','must_visit','avoid_place','constraint',"
            "'excluded_place_type','accommodation_preference','preferred_transport',"
            "'avoided_transport','clarifying_question')",
            name="ck_trip_intent_value_kind",
        ),
        sa.ForeignKeyConstraint(
            ["trip_intent_id"], ["trip_intent_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "trip_intent_id",
            "kind",
            "position",
            name="uq_trip_intent_value_position",
        ),
    )
    op.create_table(
        "trip_intent_destination_stays",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("trip_intent_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("start_day", sa.Integer(), nullable=False),
        sa.Column("end_day", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["trip_intent_id"], ["trip_intent_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "trip_intent_id",
            "position",
            name="uq_trip_intent_destination_stay_position",
        ),
    )

    op.add_column(
        "trip_chats",
        sa.Column("current_trip_intent_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_trip_chats_current_trip_intent",
        "trip_chats",
        "trip_intent_versions",
        ["current_trip_intent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "trip_chat_plan_revisions",
        sa.Column("trip_intent_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_trip_chat_revisions_trip_intent",
        "trip_chat_plan_revisions",
        "trip_intent_versions",
        ["trip_intent_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_trip_chat_plan_revisions_trip_intent_id",
        "trip_chat_plan_revisions",
        ["trip_intent_id"],
    )

    # Deliberately destructive: product requested no compatibility/fallback
    # path from the former Explorer JSON snapshots.
    op.drop_column("trip_chat_plan_revisions", "explorer_payload")
    op.drop_column("trip_chats", "current_explorer")


def downgrade() -> None:
    op.add_column(
        "trip_chats", sa.Column("current_explorer", sa.JSON(), nullable=True)
    )
    op.add_column(
        "trip_chat_plan_revisions",
        sa.Column(
            "explorer_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column(
        "trip_chat_plan_revisions", "explorer_payload", server_default=None
    )
    op.drop_index(
        "ix_trip_chat_plan_revisions_trip_intent_id",
        table_name="trip_chat_plan_revisions",
    )
    op.drop_constraint(
        "fk_trip_chat_revisions_trip_intent",
        "trip_chat_plan_revisions",
        type_="foreignkey",
    )
    op.drop_column("trip_chat_plan_revisions", "trip_intent_id")
    op.drop_constraint(
        "fk_trip_chats_current_trip_intent", "trip_chats", type_="foreignkey"
    )
    op.drop_column("trip_chats", "current_trip_intent_id")
    op.drop_table("trip_intent_destination_stays")
    op.drop_table("trip_intent_values")
    op.drop_index(
        "ix_trip_intent_chat_revision", table_name="trip_intent_versions"
    )
    op.drop_table("trip_intent_versions")
    op.drop_column("explorer_intakes", "candidate_reviews")
