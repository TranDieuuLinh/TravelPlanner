"""add long-lived YouTube transcript cache

Revision ID: 20260801_0018
Revises: 20260801_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0018"
down_revision: str | None = "20260801_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "youtube_transcript_cache",
        sa.Column("video_id", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("transcript_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("is_generated", sa.Boolean(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("video_id", "language"),
    )
    op.create_index(
        "ix_youtube_transcript_cache_video_fetched",
        "youtube_transcript_cache",
        ["video_id", "fetched_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_youtube_transcript_cache_video_fetched",
        table_name="youtube_transcript_cache",
    )
    op.drop_table("youtube_transcript_cache")
