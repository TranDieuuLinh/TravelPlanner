from datetime import datetime, timezone
from importlib import import_module

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.plans.explorer.model import (
    UrlSourceArtifact,
    YouTubeTranscriptCacheEntry,
)


def test_migration_backfills_existing_youtube_caption() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            YouTubeTranscriptCacheEntry.__table__,
            UrlSourceArtifact.__table__,
        ],
    )
    fetched_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        session.add(
            YouTubeTranscriptCacheEntry(
                video_id="caption123",
                language="vi",
                transcript_text="Hồ Hoàn Kiếm vào buổi sáng.",
                source="youtube_captions_cache",
                is_generated=True,
                fetched_at=fetched_at,
                updated_at=fetched_at,
            )
        )
        session.commit()

    migration = import_module(
        "migrations.versions.20260802_0026_add_url_source_artifacts"
    )
    original_op = migration.op
    try:
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            migration._backfill_youtube_captions()

        with Session(engine) as session:
            artifact = session.scalar(select(UrlSourceArtifact))
            assert artifact is not None
            assert artifact.source_url == (
                "https://www.youtube.com/watch?v=caption123"
            )
            assert artifact.artifact_type == "caption"
            assert artifact.language == "vi"
            assert artifact.content_text == "Hồ Hoàn Kiếm vào buổi sáng."
            assert artifact.metadata_json == {"isGenerated": True}

    finally:
        migration.op = original_op
        engine.dispose()
