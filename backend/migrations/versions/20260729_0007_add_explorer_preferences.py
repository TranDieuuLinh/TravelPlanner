"""add Explorer preference level and candidate attributes

Revision ID: 20260729_0007
Revises: 20260728_0006
Create Date: 2026-07-29 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0007"
down_revision: str | None = "20260728_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_must_place") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attributes",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column(
                "preference_level",
                sa.String(length=24),
                nullable=False,
                server_default="preferred",
            )
        )
        batch_op.create_check_constraint(
            "ck_user_must_place_preference_level",
            "preference_level IN ('mentioned', 'preferred', 'must_visit')",
        )


def downgrade() -> None:
    with op.batch_alter_table("user_must_place") as batch_op:
        batch_op.drop_constraint(
            "ck_user_must_place_preference_level",
            type_="check",
        )
        batch_op.drop_column("preference_level")
        batch_op.drop_column("attributes")
