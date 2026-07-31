from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)

from app.modules.plans.explorer.tools.url_reels.schema import (
    SpeechToTextResult,
)
from app.modules.plans.explorer.tools.url_reels.utils import (
    extract_youtube_video_id,
)


class YouTubeTranscriptExtractor:
    """Fetch public YouTube captions without downloading the video."""

    def __init__(
        self,
        api_factory: Callable[[], Any] = YouTubeTranscriptApi,
    ) -> None:
        self.api_factory = api_factory

    def fetch(
        self,
        url: str,
        *,
        languages: str | Iterable[str] | None = None,
    ) -> SpeechToTextResult | None:
        video_id = extract_youtube_video_id(url)
        if video_id is None:
            return None

        preferred_languages = self._languages(languages)
        start = time.perf_counter()
        try:
            transcript_list = self.api_factory().list(video_id)
            try:
                transcript = transcript_list.find_transcript(
                    preferred_languages
                )
            except YouTubeTranscriptApiException:
                transcript = next(iter(transcript_list), None)
                if transcript is None:
                    return None
            fetched = transcript.fetch()
        except YouTubeTranscriptApiException:
            return None

        text = "\n".join(
            snippet.text.strip()
            for snippet in fetched
            if snippet.text.strip()
        ).strip()
        if not text:
            return None

        return SpeechToTextResult(
            text=text,
            source="youtube_captions",
            language=fetched.language_code,
            status="ok",
            durationSeconds=time.perf_counter() - start,
        )

    @staticmethod
    def _languages(
        languages: str | Iterable[str] | None,
    ) -> list[str]:
        if isinstance(languages, str):
            values = languages.split(",")
        else:
            values = list(languages or ())
        normalized = [
            value.strip()
            for value in values
            if value and value.strip()
        ]
        return normalized or ["en", "vi"]
