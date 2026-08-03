"""add normalized URL source artifacts for retrieval and notes

Revision ID: 20260802_0026
Revises: 20260802_0025
"""

from collections.abc import Sequence
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from alembic import op


revision: str = "20260802_0026"
down_revision: str | None = "20260802_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "url_source_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("artifact_type", sa.String(length=16), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column(
            "language", sa.String(length=32), server_default="", nullable=False
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
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
        sa.CheckConstraint(
            "artifact_type IN ('caption', 'stt', 'ocr')",
            name="ck_url_source_artifacts_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_url",
            "artifact_type",
            "language",
            name="uq_url_source_artifacts_url_type_language",
        ),
    )
    op.create_index(
        "ix_url_source_artifacts_url_fetched",
        "url_source_artifacts",
        ["source_url", "fetched_at"],
        unique=False,
    )
    op.create_index(
        "ix_url_source_artifacts_type_fetched",
        "url_source_artifacts",
        ["artifact_type", "fetched_at"],
        unique=False,
    )
    _backfill_youtube_captions()


def _backfill_youtube_captions() -> None:
    connection = op.get_bind()
    youtube_cache = sa.table(
        "youtube_transcript_cache",
        sa.column("video_id", sa.String()),
        sa.column("language", sa.String()),
        sa.column("transcript_text", sa.Text()),
        sa.column("source", sa.String()),
        sa.column("is_generated", sa.Boolean()),
        sa.column("fetched_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = connection.execute(
        sa.select(
            youtube_cache.c.video_id,
            youtube_cache.c.language,
            youtube_cache.c.transcript_text,
            youtube_cache.c.source,
            youtube_cache.c.is_generated,
            youtube_cache.c.fetched_at,
            youtube_cache.c.updated_at,
        )
    ).mappings()
    artifacts = sa.table(
        "url_source_artifacts",
        sa.column("id", sa.String()),
        sa.column("source_url", sa.Text()),
        sa.column("platform", sa.String()),
        sa.column("artifact_type", sa.String()),
        sa.column("content_text", sa.Text()),
        sa.column("language", sa.String()),
        sa.column("source", sa.String()),
        sa.column("metadata", sa.JSON()),
        sa.column("fetched_at", sa.DateTime(timezone=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    for row in rows:
        source_url = (
            "https://www.youtube.com/watch?v=" + row["video_id"]
        )
        connection.execute(
            artifacts.insert().values(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{source_url}:caption:{row['language']}",
                    )
                ),
                source_url=source_url,
                platform="youtube",
                artifact_type="caption",
                content_text=row["transcript_text"],
                language=row["language"],
                source=row["source"],
                metadata={"isGenerated": row["is_generated"]},
                fetched_at=row["fetched_at"],
                created_at=row["fetched_at"],
                updated_at=row["updated_at"],
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_url_source_artifacts_type_fetched",
        table_name="url_source_artifacts",
    )
    op.drop_index(
        "ix_url_source_artifacts_url_fetched",
        table_name="url_source_artifacts",
    )
    op.drop_table("url_source_artifacts")
