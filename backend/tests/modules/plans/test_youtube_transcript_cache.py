from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.modules.plans.explorer.tools.url_reels.transcript_cache import (
    CachedYouTubeTranscript,
    SqlAlchemyYouTubeTranscriptCache,
)


def test_persists_and_updates_public_youtube_caption() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    cache = SqlAlchemyYouTubeTranscriptCache(
        sessionmaker(autocommit=False, autoflush=False, bind=engine)
    )
    first = CachedYouTubeTranscript(
        video_id="abc123DEF45",
        language="en",
        text="First transcript",
        source="youtube_captions",
        is_generated=True,
        fetched_at=datetime.now(timezone.utc),
    )
    cache.save(first)
    cache.save(
        CachedYouTubeTranscript(
            **{
                **first.__dict__,
                "text": "Updated transcript",
            }
        )
    )

    cached = cache.get("abc123DEF45", languages=["vi", "en"])

    assert cached is not None
    assert cached.language == "en"
    assert cached.text == "Updated transcript"
