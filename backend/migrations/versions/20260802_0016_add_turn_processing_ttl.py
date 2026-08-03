"""add turn processing ttl scaffolding

Revision ID: 20260802_0016
Revises: 20260803_0029
Create Date: 2026-08-02 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260802_0016"
down_revision: str | None = "20260803_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No DDL change: the original turns migration already created
    ``processing_started_at``. This revision only documents the staleness
    sweep contract used by ``ConversationTurnService._recover_stale_turns``.
    """
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
