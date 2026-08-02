"""add post/reel types and require a tagged location

Revision ID: 20260801_0019
Revises: 20260801_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0019"
down_revision: str | None = "20260801_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_posts",
        sa.Column("content_type", sa.String(length=16), server_default="post", nullable=False),
    )
    op.create_index("ix_user_posts_content_type", "user_posts", ["content_type"])
    op.execute(
        sa.text(
            "UPDATE user_posts SET location_name = 'Địa điểm chưa xác định' "
            "WHERE location_name IS NULL OR btrim(location_name) = ''"
        )
    )
    op.alter_column(
        "user_posts",
        "location_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.create_check_constraint(
        "ck_user_posts_content_type",
        "user_posts",
        "content_type IN ('post', 'reel')",
    )
    op.create_check_constraint(
        "ck_user_posts_location_required",
        "user_posts",
        "length(btrim(location_name)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_posts_location_required", "user_posts", type_="check")
    op.drop_constraint("ck_user_posts_content_type", "user_posts", type_="check")
    op.alter_column(
        "user_posts",
        "location_name",
        existing_type=sa.String(length=255),
        nullable=True,
    )
    op.drop_index("ix_user_posts_content_type", table_name="user_posts")
    op.drop_column("user_posts", "content_type")
