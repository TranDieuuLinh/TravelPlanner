from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from datetime import datetime, timezone
from threading import Lock
from typing import Any

import requests
from youtube_transcript_api import (
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import SpeechToTextResult
from app.modules.plans.explorer.tools.url_reels.transcript_cache import (
    CachedYouTubeTranscript,
    YouTubeTranscriptCache,
)
from app.modules.plans.explorer.tools.url_reels.transcript_worker import (
    YouTubeTranscriptWorker,
)
from app.modules.plans.explorer.tools.url_reels.utils import extract_youtube_video_id


class _CaptionRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_start = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = max(0.0, self._next_start - time.monotonic())
            if delay:
                time.sleep(delay)
            self._next_start = (
                time.monotonic()
                + settings.youtube_transcript_min_interval_seconds
            )

    def reset(self) -> None:
        with self._lock:
            self._next_start = 0.0


_caption_rate_limiter = _CaptionRateLimiter()
_inflight_guard = Lock()
_inflight: dict[tuple[str, tuple[str, ...]], Future[SpeechToTextResult]] = {}


class _TimeoutSession(requests.Session):
    def request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", settings.url_reel_network_timeout_seconds)
        return super().request(method, url, **kwargs)


def _claim_inflight(
    key: tuple[str, tuple[str, ...]],
) -> tuple[Future[SpeechToTextResult], bool]:
    with _inflight_guard:
        existing = _inflight.get(key)
        if existing is not None:
            return existing, False
        future: Future[SpeechToTextResult] = Future()
        _inflight[key] = future
        return future, True


class YouTubeTranscriptExtractor:
    """Fetch, cache and classify public YouTube caption outcomes."""

    def __init__(
        self,
        api_factory: Callable[[], Any] | None = None,
        *,
        cache: YouTubeTranscriptCache | None = None,
        worker: YouTubeTranscriptWorker | None = None,
    ) -> None:
        self.api_factory = api_factory or (
            lambda: YouTubeTranscriptApi(http_client=_TimeoutSession())
        )
        self.cache = cache
        self.worker = worker

    def fetch(
        self,
        url: str,
        *,
        languages: str | Iterable[str] | None = None,
    ) -> SpeechToTextResult:
        video_id = extract_youtube_video_id(url)
        if video_id is None:
            return _failure("invalid", "youtube_invalid_video_id")

        preferred_languages = self._languages(languages)
        cached = self._cached(video_id, preferred_languages)
        if cached is not None:
            return cached

        inflight_key = (video_id, tuple(preferred_languages))
        future, is_owner = _claim_inflight(inflight_key)
        if not is_owner:
            return future.result()
        try:
            cached = self._cached(video_id, preferred_languages)
            if cached is not None:
                future.set_result(cached)
                return cached
            result, is_generated = self._fetch_primary(
                video_id,
                preferred_languages,
            )
            if result.status in {"blocked", "unavailable"} and self.worker is not None:
                worker_result = self.worker.fetch(
                    video_id,
                    languages=preferred_languages,
                )
                if worker_result is not None:
                    result = worker_result
                    is_generated = None
            if result.status == "ok" and result.text:
                self._save(video_id, result, is_generated=is_generated)
            future.set_result(result)
            return result
        except BaseException as exc:
            future.set_exception(exc)
            raise
        finally:
            with _inflight_guard:
                if _inflight.get(inflight_key) is future:
                    _inflight.pop(inflight_key, None)

    def _fetch_primary(
        self,
        video_id: str,
        preferred_languages: list[str],
    ) -> tuple[SpeechToTextResult, bool | None]:
        start = time.perf_counter()
        try:
            _caption_rate_limiter.wait()
            transcript_list = self.api_factory().list(video_id)
            try:
                transcript = transcript_list.find_transcript(
                    preferred_languages
                )
            except NoTranscriptFound:
                transcript = next(iter(transcript_list), None)
                if transcript is None:
                    return (
                        _failure("no_captions", "youtube_no_captions", start),
                        None,
                    )
            except YouTubeTranscriptApiException:
                transcript = next(iter(transcript_list), None)
                if transcript is None:
                    return (
                        _failure("no_captions", "youtube_no_captions", start),
                        None,
                    )
            fetched = transcript.fetch()
        except (IpBlocked, RequestBlocked):
            return _failure("blocked", "youtube_ip_blocked", start), None
        except (NoTranscriptFound, TranscriptsDisabled):
            return _failure("no_captions", "youtube_no_captions", start), None
        except (InvalidVideoId, VideoUnavailable):
            return _failure("unavailable", "youtube_video_unavailable", start), None
        except requests.RequestException:
            return _failure("unavailable", "youtube_caption_unavailable", start), None
        except YouTubeTranscriptApiException:
            return _failure("unavailable", "youtube_caption_unavailable", start), None

        text = "\n".join(
            snippet.text.strip()
            for snippet in fetched
            if snippet.text.strip()
        ).strip()
        if not text:
            return _failure("no_captions", "youtube_empty_captions", start), None

        return (
            SpeechToTextResult(
                text=text,
                source="youtube_captions",
                language=fetched.language_code,
                status="ok",
                durationSeconds=time.perf_counter() - start,
            ),
            getattr(transcript, "is_generated", None),
        )

    def _cached(
        self,
        video_id: str,
        preferred_languages: list[str],
    ) -> SpeechToTextResult | None:
        if self.cache is None:
            return None
        cached = self.cache.get(video_id, languages=preferred_languages)
        if cached is None:
            return None
        return SpeechToTextResult(
            text=cached.text,
            source="youtube_captions_cache",
            language=cached.language,
            status="ok",
            durationSeconds=0.0,
        )

    def _save(
        self,
        video_id: str,
        result: SpeechToTextResult,
        *,
        is_generated: bool | None,
    ) -> None:
        if self.cache is None or not result.language:
            return
        self.cache.save(
            CachedYouTubeTranscript(
                video_id=video_id,
                language=result.language,
                text=result.text,
                source=result.source,
                is_generated=is_generated,
                fetched_at=datetime.now(timezone.utc),
            )
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


def _failure(
    status: str,
    error: str,
    started_at: float | None = None,
) -> SpeechToTextResult:
    return SpeechToTextResult(
        text="",
        source="youtube_captions",
        status=status,
        error=error,
        durationSeconds=(
            time.perf_counter() - started_at
            if started_at is not None
            else 0.0
        ),
    )
