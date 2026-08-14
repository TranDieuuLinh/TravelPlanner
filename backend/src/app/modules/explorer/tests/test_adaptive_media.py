import asyncio

from app.modules.explorer.adapters.media_analysis import (
    GeminiMediaAnalyzer,
    MediaObservation,
    MediaReadResult,
)


class UnusedClient:
    async def generate_media(self, *args, **kwargs) -> str:
        raise AssertionError("test analyzer overrides STT")


class RecordingProcessor:
    def __init__(self) -> None:
        self.chunk_counts: list[int] = []

    async def extract_audio_chunks(
        self,
        media_path: str,
        output_dir: str,
        *,
        duration_seconds: float,
        chunk_count: int,
    ) -> list[tuple[str, float]]:
        self.chunk_counts.append(chunk_count)
        return [
            (f"chunk-{index}.mp3", float(index * 60))
            for index in range(chunk_count)
        ]


class RecordingAnalyzer(GeminiMediaAnalyzer):
    async def _stt_chunk(self, path: str, index: int) -> MediaReadResult:
        return MediaReadResult(
            observations=[MediaObservation(item_index=1, text=f"chunk {index}")]
        )


def test_short_social_audio_uses_one_chunk() -> None:
    analyzer = RecordingAnalyzer(
        UnusedClient(),  # type: ignore[arg-type]
        audio_chunk_count=3,
        audio_chunk_seconds=60,
    )
    processor = RecordingProcessor()
    analyzer.ffmpeg = processor  # type: ignore[assignment]

    artifacts = asyncio.run(
        analyzer._analyze_audio("video.mp4", "/tmp", "https://example.com", 30)
    )

    assert processor.chunk_counts == [1]
    assert len(artifacts) == 1


def test_longer_social_audio_uses_up_to_configured_maximum() -> None:
    analyzer = RecordingAnalyzer(
        UnusedClient(),  # type: ignore[arg-type]
        audio_chunk_count=3,
        audio_chunk_seconds=60,
    )
    processor = RecordingProcessor()
    analyzer.ffmpeg = processor  # type: ignore[assignment]

    asyncio.run(
        analyzer._analyze_audio("video.mp4", "/tmp", "https://example.com", 150)
    )

    assert processor.chunk_counts == [3]
