"""index must-place lookup by intake and user

Revision ID: 20260728_0006
Revises: 20260728_0005
Create Date: 2026-07-28 17:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_0006"
down_revision: str | None = "20260728_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_must_place_intake")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_must_place_intake_user "
        "ON user_must_place (intake_id, user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_must_place_intake_user")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_must_place_intake "
        "ON user_must_place (intake_id)"
    )
