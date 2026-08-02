from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session, sessionmaker

from app.modules.plans.explorer.model import YouTubeTranscriptCacheEntry


@dataclass(frozen=True)
class CachedYouTubeTranscript:
    video_id: str
    language: str
    text: str
    source: str
    is_generated: bool | None
    fetched_at: datetime


class YouTubeTranscriptCache(Protocol):
    def get(
        self,
        video_id: str,
        *,
        languages: list[str],
    ) -> CachedYouTubeTranscript | None: ...

    def save(self, transcript: CachedYouTubeTranscript) -> None: ...


class SqlAlchemyYouTubeTranscriptCache:
    """Long-lived public caption cache with a fresh session per worker thread."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def get(
        self,
        video_id: str,
        *,
        languages: list[str],
    ) -> CachedYouTubeTranscript | None:
        with self.session_factory() as session:
            rows = list(
                session.scalars(
                    select(YouTubeTranscriptCacheEntry)
                    .where(YouTubeTranscriptCacheEntry.video_id == video_id)
                    .order_by(YouTubeTranscriptCacheEntry.fetched_at.desc())
                ).all()
            )
        if not rows:
            return None
        by_language = {row.language: row for row in rows}
        row = next(
            (by_language[language] for language in languages if language in by_language),
            rows[0],
        )
        return _cached(row)

    def save(self, transcript: CachedYouTubeTranscript) -> None:
        values = {
            "video_id": transcript.video_id,
            "language": transcript.language,
            "transcript_text": transcript.text,
            "source": transcript.source,
            "is_generated": transcript.is_generated,
            "fetched_at": transcript.fetched_at,
            "updated_at": datetime.now(timezone.utc),
        }
        with self.session_factory() as session:
            if session.bind is not None and session.bind.dialect.name == "postgresql":
                statement = postgresql_insert(YouTubeTranscriptCacheEntry).values(**values)
                statement = statement.on_conflict_do_update(
                    index_elements=["video_id", "language"],
                    set_={
                        key: value
                        for key, value in values.items()
                        if key not in {"video_id", "language"}
                    },
                )
                session.execute(statement)
            else:
                row = session.get(
                    YouTubeTranscriptCacheEntry,
                    (transcript.video_id, transcript.language),
                )
                if row is None:
                    session.add(YouTubeTranscriptCacheEntry(**values))
                else:
                    for key, value in values.items():
                        setattr(row, key, value)
            session.commit()


def _cached(row: YouTubeTranscriptCacheEntry) -> CachedYouTubeTranscript:
    fetched_at = row.fetched_at
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return CachedYouTubeTranscript(
        video_id=row.video_id,
        language=row.language,
        text=row.transcript_text,
        source=row.source,
        is_generated=row.is_generated,
        fetched_at=fetched_at,
    )
