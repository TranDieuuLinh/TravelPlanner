from __future__ import annotations

from dataclasses import dataclass

from youtube_transcript_api import YouTubeTranscriptApiException

from app.modules.plans.explorer.tools.url_reels.utils import (
    canonicalize_url,
    extract_youtube_video_id,
)
from app.modules.plans.explorer.tools.url_reels.youtube_transcript import (
    YouTubeTranscriptExtractor,
)


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


def test_caption_provider_failure_returns_control_to_media_fallback() -> None:
    extractor = YouTubeTranscriptExtractor(api_factory=FailingApi)

    result = extractor.fetch("https://youtu.be/abc123DEF45")

    assert result is None


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
