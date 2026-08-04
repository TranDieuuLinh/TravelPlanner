from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event

from youtube_transcript_api import (
    IpBlocked,
    TranscriptsDisabled,
    YouTubeTranscriptApiException,
)

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.transcript_cache import (
    CachedYouTubeTranscript,
)

from app.modules.plans.explorer.tools.url_reels.utils import (
    canonicalize_url,
    extract_youtube_video_id,
)
from app.modules.plans.explorer.tools.url_reels.youtube_transcript import (
    YouTubeTranscriptExtractor,
    _caption_rate_limiter,
)
from app.modules.plans.explorer.tools.url_reels import youtube_transcript as transcript_module
import pytest


@dataclass
class FakeSnippet:
    text: str


class FakeFetchedTranscript(list[FakeSnippet]):
    language_code = "vi"


class FakeTranscript:
    def fetch(self) -> FakeFetchedTranscript:
        return FakeFetchedTranscript(
            [FakeSnippet("Hồ Hoàn Kiếm"), FakeSnippet("Cà phê Đinh")]
        )


class FakeTranscriptList:
    def __init__(self, *, preferred_available: bool = True) -> None:
        self.preferred_available = preferred_available
        self.requested_languages: list[str] = []

    def find_transcript(self, languages: list[str]) -> FakeTranscript:
        self.requested_languages = languages
        if not self.preferred_available:
            raise YouTubeTranscriptApiException()
        return FakeTranscript()

    def __iter__(self):
        yield FakeTranscript()


class FakeApi:
    def __init__(self, transcript_list: FakeTranscriptList) -> None:
        self.transcript_list = transcript_list
        self.video_id: str | None = None

    def list(self, video_id: str) -> FakeTranscriptList:
        self.video_id = video_id
        return self.transcript_list


class FailingApi:
    def list(self, video_id: str) -> FakeTranscriptList:
        raise YouTubeTranscriptApiException()


@pytest.fixture(autouse=True)
def disable_caption_pacing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        settings,
        "youtube_transcript_min_interval_seconds",
        0.0,
    )
    _caption_rate_limiter.reset()
    yield
    _caption_rate_limiter.reset()


def test_extracts_youtube_caption_without_audio_download() -> None:
    transcript_list = FakeTranscriptList()
    api = FakeApi(transcript_list)
    extractor = YouTubeTranscriptExtractor(api_factory=lambda: api)

    result = extractor.fetch(
        "https://www.youtube.com/watch?v=abc123DEF45&t=12",
        languages="vi,en",
    )

    assert api.video_id == "abc123DEF45"
    assert transcript_list.requested_languages == ["vi", "en"]
    assert result is not None
    assert result.text == "Hồ Hoàn Kiếm\nCà phê Đinh"
    assert result.language == "vi"
    assert result.source == "youtube_captions"


def test_uses_any_available_caption_when_preferred_language_is_missing() -> None:
    api = FakeApi(FakeTranscriptList(preferred_available=False))
    extractor = YouTubeTranscriptExtractor(api_factory=lambda: api)

    result = extractor.fetch(
        "https://youtu.be/abc123DEF45",
        languages="en",
    )

    assert result is not None
    assert result.language == "vi"


def test_unknown_caption_provider_failure_does_not_claim_no_captions() -> None:
    extractor = YouTubeTranscriptExtractor(api_factory=FailingApi)

    result = extractor.fetch("https://youtu.be/abc123DEF45")

    assert result.status == "unavailable"
    assert result.error == "youtube_caption_unavailable"


def test_ip_block_uses_residential_worker() -> None:
    class BlockedApi:
        def list(self, video_id: str):
            raise IpBlocked(video_id)

    class Worker:
        def fetch(self, video_id: str, *, languages: list[str]):
            assert video_id == "abc123DEF45"
            assert languages == ["en", "vi"]
            from app.modules.plans.explorer.tools.url_reels.schema import SpeechToTextResult
            return SpeechToTextResult(
                text="Hoan Kiem Lake",
                source="youtube_captions_residential_worker",
                language="en",
                status="ok",
                durationSeconds=0.1,
            )

    result = YouTubeTranscriptExtractor(
        api_factory=BlockedApi,
        worker=Worker(),
    ).fetch("https://youtu.be/abc123DEF45")

    assert result.status == "ok"
    assert result.source == "youtube_captions_residential_worker"


def test_confirmed_missing_captions_has_distinct_status() -> None:
    class NoCaptionsApi:
        def list(self, video_id: str):
            raise TranscriptsDisabled(video_id)

    result = YouTubeTranscriptExtractor(
        api_factory=NoCaptionsApi
    ).fetch("https://youtu.be/abc123DEF45")

    assert result.status == "no_captions"
    assert result.error == "youtube_no_captions"


def test_cache_hit_skips_caption_provider() -> None:
    class Cache:
        def get(self, video_id: str, *, languages: list[str]):
            return CachedYouTubeTranscript(
                video_id=video_id,
                language="en",
                text="Cached Hoan Kiem Lake",
                source="youtube_captions",
                is_generated=True,
                fetched_at=datetime.now(timezone.utc),
            )

        def save(self, transcript: CachedYouTubeTranscript) -> None:
            raise AssertionError("cache hit must not be written again")

    class MustNotRun:
        def __call__(self):
            raise AssertionError("provider must not run on a cache hit")

    result = YouTubeTranscriptExtractor(
        api_factory=MustNotRun(),
        cache=Cache(),
    ).fetch("https://youtu.be/abc123DEF45")

    assert result.text == "Cached Hoan Kiem Lake"
    assert result.source == "youtube_captions_cache"


def test_concurrent_requests_share_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()
    release = Event()
    follower_claimed = Event()
    original_claim = transcript_module._claim_inflight

    def recording_claim(key):
        future, is_owner = original_claim(key)
        if not is_owner:
            follower_claimed.set()
        return future, is_owner

    monkeypatch.setattr(transcript_module, "_claim_inflight", recording_claim)

    class BlockingUnavailableApi:
        calls = 0

        def list(self, video_id: str):
            self.calls += 1
            started.set()
            assert follower_claimed.wait(timeout=2)
            assert release.wait(timeout=2)
            raise YouTubeTranscriptApiException()

    api = BlockingUnavailableApi()
    extractor = YouTubeTranscriptExtractor(api_factory=lambda: api)
    url = "https://youtu.be/abc123DEF45"

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(extractor.fetch, url)
        assert started.wait(timeout=2)
        second = executor.submit(extractor.fetch, url)
        assert follower_claimed.wait(timeout=2)
        release.set()
        results = [first.result(timeout=2), second.result(timeout=2)]

    assert api.calls == 1
    assert [result.status for result in results] == [
        "unavailable",
        "unavailable",
    ]


def test_youtube_url_parsing_and_canonicalization() -> None:
    assert (
        extract_youtube_video_id(
            "https://www.youtube.com/shorts/abc123DEF45?feature=share"
        )
        == "abc123DEF45"
    )
    assert (
        extract_youtube_video_id("https://youtu.be/abc123DEF45?t=12")
        == "abc123DEF45"
    )
    assert (
        canonicalize_url(
            "https://www.youtube.com/watch?v=abc123DEF45&utm_source=test"
        )
        == "https://www.youtube.com/watch?v=abc123DEF45"
    )
    assert extract_youtube_video_id("https://example.com/abc123DEF45") is None
