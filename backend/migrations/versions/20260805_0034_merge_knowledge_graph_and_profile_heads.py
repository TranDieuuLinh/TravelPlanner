"""merge knowledge graph and normalized profile migration heads

Revision ID: 20260805_0034
Revises: 20260804_0005, 20260805_0033
Create Date: 2026-08-05
"""

from collections.abc import Sequence


revision: str = "20260805_0034"
down_revision: tuple[str, str] = (
    "20260804_0005",
    "20260805_0033",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
