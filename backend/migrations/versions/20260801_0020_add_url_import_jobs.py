"""add persistent URL import jobs

Revision ID: 20260801_0020
Revises: 20260801_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0020"
down_revision: str | None = "20260801_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "url_import_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("request_content", sa.Text(), nullable=False),
        sa.Column("batch_position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result_revision", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["trip_chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_url_import_jobs_user_id", "url_import_jobs", ["user_id"])
    op.create_index("ix_url_import_jobs_chat_id", "url_import_jobs", ["chat_id"])
    op.create_index("ix_url_import_jobs_status", "url_import_jobs", ["status"])
    op.create_index("ix_url_import_jobs_created_at", "url_import_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_url_import_jobs_created_at", table_name="url_import_jobs")
    op.drop_index("ix_url_import_jobs_status", table_name="url_import_jobs")
    op.drop_index("ix_url_import_jobs_chat_id", table_name="url_import_jobs")
    op.drop_index("ix_url_import_jobs_user_id", table_name="url_import_jobs")
    op.drop_table("url_import_jobs")
