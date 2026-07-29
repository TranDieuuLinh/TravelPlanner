"""repair legacy users table missing auth and profile columns

Revision ID: 20260730_0008
Revises: 20260729_0007
Create Date: 2026-07-30 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0008"
down_revision: str | None = "20260729_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "users" not in set(inspector.get_table_names()):
        return
    existing = {
        column["name"]
        for column in inspector.get_columns("users")
    }
    required_columns = [
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "password_hash",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column(
            "creator_status",
            sa.String(length=32),
            nullable=False,
            server_default="none",
        ),
        sa.Column(
            "creator_portfolio_urls",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    ]
    with op.batch_alter_table("users") as batch_op:
        for column in required_columns:
            if column.name not in existing:
                batch_op.add_column(column)


def downgrade() -> None:
    # This is a corrective migration for databases that followed the duplicate
    # 0002/0003 Place branch and skipped the Auth/Profile branch. It must not
    # remove columns from databases where Auth/Profile had already created them.
    pass
