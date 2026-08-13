import asyncio

from app.modules.explorer.adapters.youtube_transcript import (
    TranscriptBundle,
    YouTubeTranscriptSourceExtractor,
    YtDlpCaptionClient,
)
from app.modules.explorer.models import SourceArtifact


def test_vtt_parser_preserves_full_timeline_and_source_url(tmp_path) -> None:
    path = tmp_path / "youtube.vi.vtt"
    path.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHồ Gươm\n\n"
        "00:05:01.000 --> 00:05:04.000\nVăn Miếu Quốc Tử Giám\n",
        encoding="utf-8",
    )

    artifacts = YtDlpCaptionClient._parse_vtt(path, "https://youtu.be/abc")

    assert "Hồ Gươm" in artifacts[0].text
    assert "Văn Miếu Quốc Tử Giám" in artifacts[0].text
    assert artifacts[0].source_url == "https://youtu.be/abc"
    assert artifacts[0].source_time_hint == "00:00:00"


def test_youtube_uses_caption_without_downloading_audio() -> None:
    class Captions:
        async def fetch(self, url: str, target_dir: str):
            return TranscriptBundle(
                artifacts=[SourceArtifact(
                    artifactType="transcript", text="Hồ Gươm", sourceUrl=url
                )],
                metadata={"title": "Hà Nội", "duration": 600},
                duration_seconds=600,
                source="youtube_caption",
            )

    class Audio:
        async def download(self, *args):
            raise AssertionError("audio fallback must not run when captions exist")

    extractor = YouTubeTranscriptSourceExtractor(Captions(), Audio(), object())
    result = asyncio.run(extractor.extract(
        "https://youtu.be/abc", source_index=0, raw_prompt=None
    ))

    assert result.coverage_status == "complete"
    assert result.coverage_ratio == 1.0
    assert any(item.artifact_type == "transcript" for item in result.artifacts)


def test_youtube_uses_audio_only_fallback_when_caption_is_missing() -> None:
    class Captions:
        async def fetch(self, url: str, target_dir: str):
            return None

    class Audio:
        called = False

        async def download(self, url: str, target_dir: str):
            self.called = True
            return f"{target_dir}/audio.m4a", {"title": "Hà Nội", "duration": 900}

    class Transcriber:
        async def transcribe(self, media_path: str, work_dir: str, source_url: str):
            return [SourceArtifact(
                artifactType="transcript", text="Văn Miếu", sourceUrl=source_url
            )], 900

    audio = Audio()
    extractor = YouTubeTranscriptSourceExtractor(Captions(), audio, Transcriber())

    result = asyncio.run(extractor.extract(
        "https://youtu.be/abc", source_index=0, raw_prompt=None
    ))

    assert audio.called is True
    assert result.coverage_ratio == 1.0
    assert any(item.text == "Văn Miếu" for item in result.artifacts)
