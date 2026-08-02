"""share URL extraction and must-place records across users

Revision ID: 20260801_0021
Revises: 20260801_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260801_0021"
down_revision: str | None = "20260801_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_user_must_place_intake_id",
        "user_must_place",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_user_must_place_intake_candidate",
        "user_must_place",
        type_="unique",
    )
    op.alter_column("user_must_place", "intake_id", nullable=True)

    columns = (
        sa.Column("place_id", sa.String(length=96), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("place_type", sa.String(length=96), nullable=True),
        sa.Column("region_key", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column(
            "opening_hours", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column("typical_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("source_platform", sa.String(length=64), nullable=True),
        sa.Column("source_link", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("plus_code", sa.String(length=64), nullable=True),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=True),
        sa.Column("source_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in columns:
        op.add_column("user_must_place", column)

    op.create_foreign_key(
        "fk_user_must_place_place_id",
        "user_must_place",
        "places",
        ["place_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_user_must_place_rating_range",
        "user_must_place",
        "rating IS NULL OR (rating >= 0 AND rating <= 5)",
    )
    op.create_check_constraint(
        "ck_user_must_place_review_count_nonnegative",
        "user_must_place",
        "review_count IS NULL OR review_count >= 0",
    )
    op.create_index(
        "ix_user_must_place_source_url",
        "user_must_place",
        ["source_url"],
    )

    # Preserve all legacy records and derive the new snapshot columns from the
    # normalized data already stored on each row.
    op.execute(
        sa.text(
            """
            UPDATE user_must_place
            SET
                name = resolved_name,
                place_type = category,
                status = CASE
                    WHEN resolution_status = 'resolved' THEN 'active'
                    ELSE 'unverified'
                END,
                typical_duration_minutes = source_duration_minutes,
                source_platform = provider,
                source_url = sources -> 0 ->> 'url',
                source_link = sources -> 0 ->> 'url',
                source_fetched_at = fetched_at,
                metadata = json_build_object(
                    'candidateName', candidate_name,
                    'sourceEvidence', source_evidence
                )
            """
        )
    )
    op.create_table(
        "user_must_place_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_must_place_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("intake_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["user_must_place_id"], ["user_must_place.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["intake_id"], ["explorer_intakes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "intake_id",
            "user_must_place_id",
            name="uq_user_must_place_users_intake_place",
        ),
    )
    op.create_index(
        "ix_user_must_place_users_user",
        "user_must_place_users",
        ["user_id", "created_at"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_must_place_users (
                id, user_must_place_id, user_id, intake_id, created_at
            )
            SELECT
                gen_random_uuid()::text,
                ump.id,
                CASE
                    WHEN ump.user_id ~ '^[0-9]+$' THEN ump.user_id::integer
                    ELSE NULL
                END,
                ump.intake_id,
                ump.created_at
            FROM user_must_place AS ump
            WHERE ump.intake_id IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH duplicate_map AS (
                SELECT
                    id,
                    first_value(id) OVER (
                        PARTITION BY source_url, candidate_key
                        ORDER BY created_at, id
                    ) AS keeper_id
                FROM user_must_place
                WHERE source_url IS NOT NULL
            )
            UPDATE user_must_place_users AS link
            SET user_must_place_id = duplicate_map.keeper_id
            FROM duplicate_map
            WHERE link.user_must_place_id = duplicate_map.id
              AND duplicate_map.id <> duplicate_map.keeper_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM user_must_place AS duplicate
            USING user_must_place AS keeper
            WHERE duplicate.source_url IS NOT NULL
              AND duplicate.source_url = keeper.source_url
              AND duplicate.candidate_key = keeper.candidate_key
              AND (duplicate.created_at, duplicate.id) > (keeper.created_at, keeper.id)
            """
        )
    )
    op.create_unique_constraint(
        "uq_user_must_place_source_candidate",
        "user_must_place",
        ["source_url", "candidate_key"],
    )

    op.create_table(
        "url_extraction_cache",
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("extracted_context", sa.JSON(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("source_url"),
    )


def downgrade() -> None:
    op.drop_table("url_extraction_cache")
    op.drop_index(
        "ix_user_must_place_users_user", table_name="user_must_place_users"
    )
    op.drop_table("user_must_place_users")
    op.drop_index("ix_user_must_place_source_url", table_name="user_must_place")
    op.drop_constraint(
        "uq_user_must_place_source_candidate",
        "user_must_place",
        type_="unique",
    )
    op.drop_constraint(
        "ck_user_must_place_review_count_nonnegative",
        "user_must_place",
        type_="check",
    )
    op.drop_constraint(
        "ck_user_must_place_rating_range",
        "user_must_place",
        type_="check",
    )
    op.drop_constraint(
        "fk_user_must_place_place_id", "user_must_place", type_="foreignkey"
    )
    for column in (
        "deleted_at",
        "metadata",
        "revision",
        "source_fetched_at",
        "review_count",
        "rating",
        "plus_code",
        "source_url",
        "source_link",
        "source_platform",
        "typical_duration_minutes",
        "opening_hours",
        "status",
        "region_key",
        "place_type",
        "name",
        "place_id",
    ):
        op.drop_column("user_must_place", column)
    op.alter_column("user_must_place", "intake_id", nullable=False)
    op.create_foreign_key(
        "fk_user_must_place_intake_id",
        "user_must_place",
        "explorer_intakes",
        ["intake_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_user_must_place_intake_candidate",
        "user_must_place",
        ["intake_id", "candidate_key"],
    )
