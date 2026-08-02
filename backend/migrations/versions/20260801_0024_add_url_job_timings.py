"""persist timing reports on each URL import job

Revision ID: 20260801_0024
Revises: 20260801_0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0024"
down_revision: str | None = "20260801_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_import_jobs",
        sa.Column("explorer_timing", sa.JSON(), nullable=True),
    )
    op.add_column(
        "url_import_jobs",
        sa.Column("planner_timing", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("url_import_jobs", "planner_timing")
    op.drop_column("url_import_jobs", "explorer_timing")
