"""retire the duplicate conversation-turn migration

The conversation-turn DDL is represented by the later
``20260803_0028`` migration. This file previously reused the revision ID
``20260801_0015`` and pointed back to ``20260801_0024``, creating an Alembic
cycle with the travel-groups chain.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260803_0029"
down_revision: str | None = "20260803_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
