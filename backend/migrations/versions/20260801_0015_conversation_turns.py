"""add conversation turn supervisor tables and chat scoped columns

Revision ID: 20260801_0015
Revises: 20260801_0024
Create Date: 2026-08-01 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0015"
down_revision: str | None = "20260801_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trip_chats",
        sa.Column("conversation_phase", sa.String(length=32), nullable=False, server_default="discovery"),
    )
    op.add_column(
        "trip_chats",
        sa.Column("conversation_context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column(
        "trip_chats",
        sa.Column("active_pending_turn_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "trip_chat_messages",
        sa.Column("turn_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "trip_chat_messages",
        sa.Column("message_kind", sa.String(length=32), nullable=False, server_default="text"),
    )
    op.add_column(
        "trip_chat_messages",
        sa.Column("content_blocks", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.create_index(
        "ix_trip_chat_messages_turn_id",
        "trip_chat_messages",
        ["turn_id"],
    )

    op.create_table(
        "trip_chat_turns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("chat_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_turn_id", sa.String(length=72), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("attachment_names", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("proposed_operations", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("assistant_blocks", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("result_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["trip_chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "client_turn_id", name="uq_trip_chat_turn_client_id"),
    )
    op.create_index("ix_trip_chat_turns_chat_id", "trip_chat_turns", ["chat_id"])
    op.create_index("ix_trip_chat_turns_user_id", "trip_chat_turns", ["user_id"])
    op.create_index("ix_trip_chat_turns_status", "trip_chat_turns", ["status"])
    op.create_index(
        "ix_trip_chat_turns_processing_started_at",
        "trip_chat_turns",
        ["processing_started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_trip_chat_turns_processing_started_at", table_name="trip_chat_turns")
    op.drop_index("ix_trip_chat_turns_status", table_name="trip_chat_turns")
    op.drop_index("ix_trip_chat_turns_user_id", table_name="trip_chat_turns")
    op.drop_index("ix_trip_chat_turns_chat_id", table_name="trip_chat_turns")
    op.drop_table("trip_chat_turns")
    op.drop_index("ix_trip_chat_messages_turn_id", table_name="trip_chat_messages")
    op.drop_column("trip_chat_messages", "content_blocks")
    op.drop_column("trip_chat_messages", "message_kind")
    op.drop_column("trip_chat_messages", "turn_id")
    op.drop_column("trip_chats", "active_pending_turn_id")
    op.drop_column("trip_chats", "conversation_context")
    op.drop_column("trip_chats", "conversation_phase")
