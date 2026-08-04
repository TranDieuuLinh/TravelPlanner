"""merge relationship_type rename with knowledge graph tables

Revision ID: 20260804_0002
Revises: 20260802_0016, 20260804_0001
Create Date: 2026-08-04 11:20:00
"""

from collections.abc import Sequence


revision: str = "20260804_0002"
down_revision: tuple[str, str] = (
    "20260802_0016",
    "20260804_0001",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
