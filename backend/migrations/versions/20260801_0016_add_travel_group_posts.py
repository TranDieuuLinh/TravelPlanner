"""add travel group posts

Revision ID: 20260801_0016
Revises: 20260801_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0016"
down_revision: str | None = "20260801_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "travel_group_posts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("travel_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_travel_group_posts_group_id", "travel_group_posts", ["group_id"])
    op.create_index("ix_travel_group_posts_author_id", "travel_group_posts", ["author_id"])
    op.create_index("ix_travel_group_posts_created_at", "travel_group_posts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_travel_group_posts_created_at", table_name="travel_group_posts")
    op.drop_index("ix_travel_group_posts_author_id", table_name="travel_group_posts")
    op.drop_index("ix_travel_group_posts_group_id", table_name="travel_group_posts")
    op.drop_table("travel_group_posts")
