"""merge import repair and knowledge entity tag heads

Revision ID: 20260810_0050
Revises: 20260808_0048, 20260810_0049
Create Date: 2026-08-10
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260810_0050"
down_revision: tuple[str, str] = ("20260808_0048", "20260810_0049")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge both already-applied schema branches."""


def downgrade() -> None:
    """Split the history back into its two parent heads."""
