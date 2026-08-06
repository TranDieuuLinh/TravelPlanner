"""add trip intent optimistic version and plan sync state

Revision ID: 20260806_0044
Revises: 20260805_0043
Create Date: 2026-08-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_0044"
down_revision: str | None = "20260805_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trip_chats",
        sa.Column(
            "trip_intent_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "trip_chats",
        sa.Column(
            "trip_intent_plan_status",
            sa.String(length=32),
            nullable=False,
            server_default="synced",
        ),
    )


def downgrade() -> None:
    op.drop_column("trip_chats", "trip_intent_plan_status")
    op.drop_column("trip_chats", "trip_intent_version")
