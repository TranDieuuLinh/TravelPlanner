"""merge the reverted embedding marker with the active migration chain

Revision ID: 20260802_0025
Revises: 20260801_0024, 20260801_0004
Create Date: 2026-08-02 17:05:00
"""

from collections.abc import Sequence


revision: str = "20260802_0025"
down_revision: tuple[str, str] = (
    "20260801_0024",
    "20260801_0004",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
