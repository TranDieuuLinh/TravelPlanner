"""persist latest trip chat timing reports

Revision ID: 20260801_0022
Revises: 20260801_0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0022"
down_revision: str | None = "20260801_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trip_chats",
        sa.Column("latest_explorer_timing", sa.JSON(), nullable=True),
    )
    op.add_column(
        "trip_chats",
        sa.Column("latest_planner_timing", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trip_chats", "latest_planner_timing")
    op.drop_column("trip_chats", "latest_explorer_timing")
