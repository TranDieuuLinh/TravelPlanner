import asyncio

from app.modules.explorer.adapters.media_analysis import GeminiMediaAnalyzer


class FakeMediaClient:
    async def generate_media(self, *args, **kwargs) -> str:
        return '{"observations":[]}'


class VideoOnlyProcessor:
    async def duration_seconds(self, media_path: str) -> float:
        return 10

    async def stream_types(self, media_path: str) -> set[str]:
        return {"video"}


class VideoAndAudioProcessor(VideoOnlyProcessor):
    async def stream_types(self, media_path: str) -> set[str]:
        return {"video", "audio"}


class RecordingAnalyzer(GeminiMediaAnalyzer):
    def __init__(self):
        super().__init__(FakeMediaClient())
        self.frame_calls = 0
        self.audio_calls = 0

    async def _analyze_frames(self, *args, **kwargs):
        self.frame_calls += 1
        return []

    async def _analyze_audio(self, *args, **kwargs):
        self.audio_calls += 1
        return []


def test_media_analyzer_skips_stt_when_media_has_no_audio(tmp_path) -> None:
    analyzer = RecordingAnalyzer()
    analyzer.ffmpeg = VideoOnlyProcessor()

    result = asyncio.run(analyzer.analyze(
        "video.mp4", str(tmp_path), "https://example.com/video"
    ))

    assert result.failures == []
    assert analyzer.frame_calls == 1
    assert analyzer.audio_calls == 0


def test_media_analyzer_can_run_only_requested_ocr_branch(tmp_path) -> None:
    analyzer = RecordingAnalyzer()
    analyzer.ffmpeg = VideoAndAudioProcessor()

    result = asyncio.run(analyzer.analyze(
        "video.mp4",
        str(tmp_path),
        "https://example.com/video",
        branches={"frame_ocr"},
    ))

    assert result.failures == []
    assert analyzer.frame_calls == 1
    assert analyzer.audio_calls == 0
