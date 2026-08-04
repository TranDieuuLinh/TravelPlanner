"""add per-user trip chat history and plan revisions

Revision ID: 20260730_0011
Revises: 20260730_0010
Create Date: 2026-07-30 14:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260730_0011"
down_revision: str | None = "20260730_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trip_chats",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=True),
        sa.Column("current_plan", sa.JSON(), nullable=True),
        sa.Column("current_explorer", sa.JSON(), nullable=True),
        sa.Column("current_intake_id", sa.String(length=36), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_chats_user_id", "trip_chats", ["user_id"])
    op.create_index("ix_trip_chats_updated_at", "trip_chats", ["updated_at"])
    op.create_table(
        "trip_chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chat_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("attachment_names", sa.JSON(), nullable=False),
        sa.Column("plan_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["trip_chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "sequence", name="uq_trip_chat_message_sequence"),
    )
    op.create_index("ix_trip_chat_messages_chat_id", "trip_chat_messages", ["chat_id"])
    op.create_table(
        "trip_chat_plan_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chat_id", sa.String(length=36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("plan_payload", sa.JSON(), nullable=False),
        sa.Column("explorer_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["trip_chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "revision", name="uq_trip_chat_revision"),
    )
    op.create_index("ix_trip_chat_plan_revisions_chat_id", "trip_chat_plan_revisions", ["chat_id"])


def downgrade() -> None:
    op.drop_index("ix_trip_chat_plan_revisions_chat_id", table_name="trip_chat_plan_revisions")
    op.drop_table("trip_chat_plan_revisions")
    op.drop_index("ix_trip_chat_messages_chat_id", table_name="trip_chat_messages")
    op.drop_table("trip_chat_messages")
    op.drop_index("ix_trip_chats_updated_at", table_name="trip_chats")
    op.drop_index("ix_trip_chats_user_id", table_name="trip_chats")
    op.drop_table("trip_chats")
