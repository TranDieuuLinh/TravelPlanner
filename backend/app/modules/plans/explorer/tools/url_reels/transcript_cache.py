from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.plans.explorer.model import SourceDocument


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
            canonical_url = _youtube_url(video_id)
            document = session.scalar(
                select(SourceDocument).where(
                    SourceDocument.canonical_url == canonical_url
                )
            )
            if document is None:
                return None
            caption_artifacts = dict(
                (document.artifacts_json or {}).get("caption") or {}
            )
            if not caption_artifacts:
                return None
            language = next(
                (value for value in languages if value in caption_artifacts),
                next(iter(caption_artifacts)),
            )
            artifact = dict(caption_artifacts[language] or {})
            fetched_at = document.fetched_at
        if not artifact.get("text"):
            return None
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        metadata = dict(artifact.get("metadata") or {})
        return CachedYouTubeTranscript(
            video_id=video_id,
            language="" if language == "_" else language,
            text=str(artifact["text"]),
            source=str(artifact.get("source") or "youtube_captions"),
            is_generated=metadata.get("isGenerated"),
            fetched_at=fetched_at,
        )

    def save(self, transcript: CachedYouTubeTranscript) -> None:
        with self.session_factory() as session:
            canonical_url = _youtube_url(transcript.video_id)
            document = session.scalar(
                select(SourceDocument).where(
                    SourceDocument.canonical_url == canonical_url
                )
            )
            if document is None:
                document = SourceDocument(
                    id=str(uuid4()),
                    canonical_url=canonical_url,
                    platform="youtube",
                    artifacts_json={},
                    extracted_context_json={},
                )
                session.add(document)
            artifacts = dict(document.artifacts_json or {})
            captions = dict(artifacts.get("caption") or {})
            captions[transcript.language or "_"] = {
                "text": transcript.text,
                "source": transcript.source,
                "metadata": {
                    "videoId": transcript.video_id,
                    "isGenerated": transcript.is_generated,
                },
            }
            artifacts["caption"] = captions
            document.artifacts_json = artifacts
            document.fetched_at = transcript.fetched_at
            document.updated_at = datetime.now(timezone.utc)
            session.commit()


def _youtube_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
