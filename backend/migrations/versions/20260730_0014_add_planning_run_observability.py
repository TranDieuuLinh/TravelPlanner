"""add planning run observability

Revision ID: 20260730_0014
Revises: 20260730_0013
Create Date: 2026-07-30 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260730_0014"
down_revision: str | None = "20260730_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planning_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("intake_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("current_stage", sa.String(length=32), nullable=True),
        sa.Column("stage_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planning_runs_user_id", "planning_runs", ["user_id"])
    op.create_index(
        "ix_planning_runs_created_status",
        "planning_runs",
        ["created_at", "status"],
    )
    op.create_index(
        "ix_planning_runs_intake_id",
        "planning_runs",
        ["intake_id"],
    )

    op.create_table(
        "planning_run_stages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["planning_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "sequence",
            name="uq_planning_run_stages_run_sequence",
        ),
    )
    op.create_index(
        "ix_planning_run_stages_run_stage",
        "planning_run_stages",
        ["run_id", "stage"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_planning_run_stages_run_stage",
        table_name="planning_run_stages",
    )
    op.drop_table("planning_run_stages")
    op.drop_index("ix_planning_runs_intake_id", table_name="planning_runs")
    op.drop_index("ix_planning_runs_created_status", table_name="planning_runs")
    op.drop_index("ix_planning_runs_user_id", table_name="planning_runs")
    op.drop_table("planning_runs")
