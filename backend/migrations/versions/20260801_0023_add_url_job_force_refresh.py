"""add force refresh mode to URL import jobs

Revision ID: 20260801_0023
Revises: 20260801_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0023"
down_revision: str | None = "20260801_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "url_import_jobs",
        sa.Column(
            "force_refresh",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("url_import_jobs", "force_refresh")
