import asyncio

from app.modules.explorer.adapters.youtube_transcript import (
    TranscriptBundle,
    YtDlpCaptionClient,
)
from app.modules.explorer.adapters.youtube_source import (
    YouTubeTranscriptSourceExtractor,
)
from app.modules.explorer.models import SourceArtifact
from app.modules.explorer.ports import DownloadedMedia
from app.modules.explorer.primary_coverage import PrimaryEvidenceCoverage


def coverage(sufficient: bool) -> PrimaryEvidenceCoverage:
    return PrimaryEvidenceCoverage(
        sufficient=sufficient,
        transcript_timeline_ratio=None,
        meaningful_character_count=100,
        destination_found=sufficient,
        named_place_count=2 if sufficient else 0,
        travel_detail_count=2 if sufficient else 0,
        description_useful=sufficient,
        confidence=0.9,
        reasons=("test",),
    )


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


def test_youtube_sources_are_serialized_by_default() -> None:
    class Captions:
        active = 0
        maximum = 0

        async def fetch(self, url: str, target_dir: str):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return TranscriptBundle(
                artifacts=[SourceArtifact(
                    artifactType="transcript", text="Hà Nội", sourceUrl=url
                )],
                metadata={"title": "Hà Nội", "duration": 60},
                duration_seconds=60,
                source="youtube_caption",
            )

    captions = Captions()
    extractor = YouTubeTranscriptSourceExtractor(captions, object(), object())

    async def run():
        await asyncio.gather(*(
            extractor.extract(
                f"https://youtu.be/{index}", source_index=index, raw_prompt=None
            )
            for index in range(3)
        ))

    asyncio.run(run())

    assert captions.maximum == 1


def test_youtube_metadata_can_skip_stt_when_semantically_sufficient() -> None:
    class Captions:
        async def fetch(self, url: str, target_dir: str):
            return TranscriptBundle(
                artifacts=[],
                metadata={
                    "title": "Hà Nội",
                    "description": "Hồ Gươm, Văn Miếu, mở cửa 8 giờ, vé 30.000 đồng",
                    "duration": 60,
                },
                duration_seconds=60,
                source="youtube_metadata",
            )

    class Evaluator:
        async def evaluate(self, artifacts, **kwargs):
            return coverage(True)

    class Audio:
        async def download(self, *args):
            raise AssertionError("sufficient metadata must skip STT")

    extractor = YouTubeTranscriptSourceExtractor(
        Captions(),
        Audio(),
        object(),
        coverage_evaluator=Evaluator(),
    )
    result = asyncio.run(extractor.extract(
        "https://youtu.be/abc",
        source_index=0,
        raw_prompt=None,
    ))

    assert result.status == "succeeded"
    assert result.coverage_status == "unknown"
    assert any(item.artifact_type == "caption" for item in result.artifacts)


def test_youtube_sparse_caption_runs_ocr_without_duplicate_stt() -> None:
    class Captions:
        async def fetch(self, url: str, target_dir: str):
            return TranscriptBundle(
                artifacts=[SourceArtifact(
                    artifactType="transcript", text="Đi thôi", sourceUrl=url
                )],
                metadata={"title": "Một ngày đi chơi", "duration": 60},
                duration_seconds=60,
                source="youtube_caption",
            )

    class Evaluator:
        async def evaluate(self, artifacts, **kwargs):
            return coverage(False)

    class Audio:
        async def download(self, *args):
            raise AssertionError("native caption must not trigger duplicate STT")

    class Media:
        async def download(self, url: str, target_dir: str):
            return DownloadedMedia(f"{target_dir}/video.mp4", {})

    class Analyzer:
        async def analyze(self, media_path, work_dir, source_url, *, branches=None):
            assert branches == {"frame_ocr"}
            from app.modules.explorer.models import MediaAnalysisResult

            return MediaAnalysisResult(artifacts=[SourceArtifact(
                artifactType="frame_ocr", text="Văn Miếu", sourceUrl=source_url
            )])

    extractor = YouTubeTranscriptSourceExtractor(
        Captions(),
        Audio(),
        object(),
        coverage_evaluator=Evaluator(),
        media_client=Media(),
        analyzer=Analyzer(),
    )
    result = asyncio.run(extractor.extract(
        "https://youtu.be/abc",
        source_index=0,
        raw_prompt=None,
    ))

    assert any(item.artifact_type == "frame_ocr" for item in result.artifacts)
