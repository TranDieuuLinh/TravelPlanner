"""recognize the reverted experimental embedding revision

Revision ID: 20260801_0004
Revises: 20260731_0003
Create Date: 2026-08-02 17:00:00

Some development databases applied the former place-embedding migration before
that feature was reverted. The physical vector column may therefore still be
present in those databases. This no-op compatibility marker lets Alembic read
their version table without reintroducing embedding behavior into the app.
"""

from collections.abc import Sequence


revision: str = "20260801_0004"
down_revision: str | None = "20260731_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
