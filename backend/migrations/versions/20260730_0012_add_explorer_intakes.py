"""add Explorer intake identity and revision provenance

Revision ID: 20260730_0012
Revises: 20260730_0011
Create Date: 2026-07-30 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260730_0012"
down_revision: str | None = "20260730_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explorer_intakes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("destination", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_explorer_intakes_user_created",
        "explorer_intakes",
        ["user_id", "created_at"],
    )

    # Preserve existing must-place rows before enforcing the new parent FK.
    op.execute(
        sa.text(
            """
            INSERT INTO explorer_intakes (id, user_id, destination, created_at)
            SELECT
                intake_id,
                MAX(user_id),
                MAX(destination),
                MIN(created_at)
            FROM user_must_place
            GROUP BY intake_id
            """
        )
    )
    # An intake can legitimately have no resolved must-place. Retain the latest
    # intake referenced by each existing trip chat as a parent record too.
    op.execute(
        sa.text(
            """
            INSERT INTO explorer_intakes (id, user_id, destination, created_at)
            SELECT
                tc.current_intake_id,
                CAST(tc.user_id AS VARCHAR(64)),
                COALESCE(tc.destination, 'unspecified'),
                tc.updated_at
            FROM trip_chats AS tc
            WHERE tc.current_intake_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM explorer_intakes AS ei
                  WHERE ei.id = tc.current_intake_id
              )
            """
        )
    )
    op.create_foreign_key(
        "fk_user_must_place_intake_id",
        "user_must_place",
        "explorer_intakes",
        ["intake_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "trip_chat_plan_revisions",
        sa.Column("intake_id", sa.String(length=36), nullable=True),
    )
    # Only the current revision can be mapped reliably from legacy chat rows.
    # Older snapshots stay nullable rather than receiving incorrect provenance.
    op.execute(
        sa.text(
            """
            UPDATE trip_chat_plan_revisions AS revision
            SET intake_id = chat.current_intake_id
            FROM trip_chats AS chat
            WHERE revision.chat_id = chat.id
              AND revision.revision = chat.revision
            """
        )
    )
    op.create_index(
        "ix_trip_chat_plan_revisions_intake_id",
        "trip_chat_plan_revisions",
        ["intake_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trip_chat_plan_revisions_intake_id",
        table_name="trip_chat_plan_revisions",
    )
    op.drop_column("trip_chat_plan_revisions", "intake_id")
    op.drop_constraint(
        "fk_user_must_place_intake_id",
        "user_must_place",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_explorer_intakes_user_created",
        table_name="explorer_intakes",
    )
    op.drop_table("explorer_intakes")
