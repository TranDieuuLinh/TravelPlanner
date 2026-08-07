"""add durable traveler preference observation jobs

Revision ID: 20260807_0047
Revises: 20260807_0046
Create Date: 2026-08-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260807_0047"
down_revision: str | None = "20260807_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preference_observation_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed','skipped')",
            name="ck_preference_observation_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["trip_chat_messages.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index(
        "ix_preference_observation_jobs_message_id",
        "preference_observation_jobs",
        ["message_id"],
    )
    op.create_index(
        "ix_preference_observation_jobs_user_id",
        "preference_observation_jobs",
        ["user_id"],
    )
    op.create_index(
        "ix_preference_observation_jobs_status",
        "preference_observation_jobs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_preference_observation_jobs_status",
        table_name="preference_observation_jobs",
    )
    op.drop_index(
        "ix_preference_observation_jobs_user_id",
        table_name="preference_observation_jobs",
    )
    op.drop_index(
        "ix_preference_observation_jobs_message_id",
        table_name="preference_observation_jobs",
    )
    op.drop_table("preference_observation_jobs")
