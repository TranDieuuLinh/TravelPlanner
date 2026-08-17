import asyncio
from pathlib import Path

from app.modules.explorer.adapters import url_sources
from app.modules.explorer.adapters.media_analysis import GeminiMediaAnalyzer
from app.modules.explorer.adapters.image_source import GeminiImageSourceExtractor
from app.modules.explorer.adapters.url_sources import (
    PythonYtDlpMediaClient,
    UrlSourceRouter,
    YtDlpMetadataSourceExtractor,
    YtDlpSocialSourceExtractor,
)
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import (
    ExplorerDraft,
    MediaAnalysisResult,
    SourceArtifact,
    SourceBranchFailure,
    SourceExtractionResult,
)
from app.modules.explorer.ports import DownloadedMedia
from app.modules.explorer.service import ExplorerService
from app.shared.contracts.agent import AgentError


class FakeMetadataClient:
    async def extract(self, url: str) -> dict:
        return {"title": "Hanoi guide", "description": "Useful Hanoi caption"}


class FakeAnalyzer:
    async def analyze_image(self, data_base64: str, mime_type: str) -> str:
        assert mime_type == "image/png"
        return "Hanoi, Temple of Literature"


class FakeMediaClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def generate_media(self, *args, **kwargs) -> str:
        self.calls += 1
        return '{"observations":[{"item_index":1,"text":"' + self.text + '"}]}'


class NamedExtractor:
    def __init__(self, name: str) -> None:
        self.name = name

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        return self.name


def test_router_dispatches_platforms() -> None:
    router = UrlSourceRouter(
        youtube=NamedExtractor("youtube"),
        tiktok=NamedExtractor("tiktok"),
        instagram=NamedExtractor("instagram"),
        website=NamedExtractor("website"),
    )

    async def invoke(url):
        return await router.extract(url, source_index=0, raw_prompt=None)

    assert asyncio.run(invoke("https://youtu.be/abc")) == "youtube"
    assert asyncio.run(invoke("https://www.tiktok.com/@a/video/1")) == "tiktok"
    assert asyncio.run(invoke("https://instagram.com/reel/abc")) == "instagram"
    assert asyncio.run(invoke("https://example.com/article")) == "website"


def test_social_ytdlp_matches_legacy_standard_chrome_android_order(monkeypatch) -> None:
    import yt_dlp

    attempted_options = []

    class FakeDownloader:
        def __init__(self, options) -> None:
            attempted_options.append(options)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def extract_info(self, url: str, *, download: bool):
            assert "?" not in url
            if len(attempted_options) < 3:
                raise yt_dlp.utils.YoutubeDLError("blocked")
            return {"title": "Hanoi"}

        def sanitize_info(self, info):
            return info

    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeDownloader)
    result = url_sources._ytdlp_extract(
        "https://www.tiktok.com/@creator/video/1", {}, download=False
    )

    assert result == {"title": "Hanoi"}
    assert [
        str(options["impersonate"]) if "impersonate" in options else None
        for options in attempted_options
    ] == [
        None, "chrome", "chrome-131:android-14"
    ]


def test_social_media_prefers_small_muxed_mp4(tmp_path, monkeypatch) -> None:
    captured_options = {}

    def fake_extract(url: str, options: dict, *, download: bool):
        captured_options.update(options)
        output = options["outtmpl"].replace("%(ext)s", "mp4")
        Path(output).write_bytes(b"video")
        return {"title": "Hanoi"}

    monkeypatch.setattr(url_sources, "_ytdlp_extract", fake_extract)
    client = PythonYtDlpMediaClient()
    result = client._download_sync(
        "https://www.tiktok.com/@creator/video/1", str(tmp_path)
    )

    assert captured_options["format"] == "worst[ext=mp4]/worst"
    assert captured_options["concurrent_fragment_downloads"] == 4
    assert result.file_path.endswith("media.mp4")


def test_youtube_metadata_returns_caption_artifact_without_stt() -> None:
    extractor = YtDlpMetadataSourceExtractor(FakeMetadataClient(), platform="YouTube")
    result = asyncio.run(extractor.extract(
        "https://youtube.com/watch?v=abc", source_index=0, raw_prompt=None
    ))

    assert [item.artifact_type for item in result.artifacts] == [
        "url_metadata", "caption"
    ]
    assert all(item.artifact_type not in {"stt", "frame_ocr"} for item in result.artifacts)


def test_base64_image_uses_gemini_ocr_artifact() -> None:
    from app.modules.explorer.public import ExplorerImageInput

    extractor = GeminiImageSourceExtractor(FakeAnalyzer())
    result = asyncio.run(extractor.extract(
        ExplorerImageInput(
            fileName="itinerary.png", mimeType="image/png", dataBase64="YWJj"
        ),
        source_index=0,
        raw_prompt=None,
    ))

    assert result.artifacts[0].artifact_type == "image_ocr"
    assert "Temple of Literature" in result.artifacts[0].text


def test_media_analyzer_routes_vision_and_audio_to_separate_clients(tmp_path) -> None:
    vision = FakeMediaClient("Văn Miếu")
    audio = FakeMediaClient("Hồ Gươm")
    analyzer = GeminiMediaAnalyzer(vision, audio_client=audio)
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    assert "Văn Miếu" in asyncio.run(analyzer.analyze_image("YWJj", "image/png"))
    result = asyncio.run(analyzer._stt_chunk(str(audio_path), 0))

    assert result.observations[0].text == "Hồ Gươm"
    assert vision.calls == 1
    assert audio.calls == 1


def test_frame_batches_never_exceed_ten_images() -> None:
    frames = [f"frame-{index}.jpg" for index in range(72)]

    batches = GeminiMediaAnalyzer._batches(frames, 10)

    assert len(batches) == 8
    assert max(map(len, batches)) == 10
    assert [item for batch in batches for item in batch] == frames


def test_frame_extraction_receives_hard_limit_of_72() -> None:
    class RecordingProcessor:
        def __init__(self) -> None:
            self.max_frames = None

        async def extract_frames(self, *args, **kwargs):
            self.max_frames = kwargs["max_frames"]
            return []

    processor = RecordingProcessor()
    analyzer = GeminiMediaAnalyzer(FakeMediaClient("unused"), max_frames=72)
    analyzer.ffmpeg = processor

    artifacts = asyncio.run(analyzer._analyze_frames(
        "video.mp4", "/tmp", "https://example.com/video", 180
    ))

    assert artifacts == []
    assert processor.max_frames == 72


def test_media_analyzer_preserves_each_branch_failure(tmp_path, caplog) -> None:
    class FailingAnalyzer(GeminiMediaAnalyzer):
        async def _analyze_frames(self, *args, **kwargs):
            raise ExplorerOperationError(
                "FRAME_EXTRACTION_FAILED", "frame failed"
            )

        async def _analyze_audio(self, *args, **kwargs):
            raise ExplorerOperationError(
                "MEDIA_ANALYSIS_FAILED", "audio failed", retryable=True
            )

    class DurationOnlyProcessor:
        async def duration_seconds(self, media_path: str) -> float:
            return 30

        async def stream_types(self, media_path: str) -> set[str]:
            return {"video", "audio"}

    analyzer = FailingAnalyzer(FakeMediaClient("unused"))
    analyzer.ffmpeg = DurationOnlyProcessor()
    result = asyncio.run(analyzer.analyze(
        "video.mp4", str(tmp_path), "https://example.com/video"
    ))

    assert result.artifacts == []
    assert [failure.branch for failure in result.failures] == ["frame_ocr", "stt"]
    assert [failure.error.code for failure in result.failures] == [
        "FRAME_EXTRACTION_FAILED", "MEDIA_ANALYSIS_FAILED"
    ]
    assert "branch=frame_ocr" in caplog.text
    assert "branch=stt" in caplog.text


def test_social_source_keeps_metadata_when_media_branch_is_partial() -> None:
    class FakeDownloader:
        async def download(self, url: str, target_dir: str) -> DownloadedMedia:
            return DownloadedMedia(
                file_path=f"{target_dir}/video.mp4",
                metadata={"description": "Danh sách địa điểm Hà Nội"},
            )

    class PartialAnalyzer:
        async def analyze(self, media_path: str, work_dir: str, source_url: str):
            return MediaAnalysisResult(
                failures=[SourceBranchFailure(
                    branch="frame_ocr",
                    error=AgentError(
                        code="MEDIA_ANALYSIS_FAILED",
                        message="frame failed",
                        retryable=True,
                    ),
                )]
            )

    extractor = YtDlpSocialSourceExtractor(
        FakeDownloader(), PartialAnalyzer(), platform="TikTok"
    )
    result = asyncio.run(extractor.extract(
        "https://www.tiktok.com/@creator/video/1",
        source_index=0,
        raw_prompt=None,
    ))

    assert result.status == "partial"
    assert result.artifacts[0].artifact_type == "caption"
    assert result.branch_failures[0].error.code == "MEDIA_ANALYSIS_FAILED"


def test_partial_output_identifies_failed_source_without_echoing_query() -> None:
    service = ExplorerService(None, None, None, None)  # type: ignore[arg-type]
    failed = SourceExtractionResult(
        sourceIndex=1,
        sourceKind="url",
        sourceRef="https://www.klook.com/vi/blog/post/?tracking=private",
        status="failed_permanent",
        error=AgentError(code="WEB_DOWNLOAD_FAILED", message="blocked"),
    )

    output = service.finalize(
        intake_id="intake-1",
        draft=ExplorerDraft(inputAdm="Hà Nội"),
        input_adm="Hà Nội",
        adm_conflict=False,
        prompt_days=None,
        coverage="partial",
        source_results=[failed],
    )

    assert "klook.com" in output.warnings[1]
    assert "tracking" not in output.warnings[1]


def test_partial_output_identifies_failed_media_branch() -> None:
    service = ExplorerService(None, None, None, None)  # type: ignore[arg-type]
    partial = SourceExtractionResult(
        sourceIndex=0,
        sourceKind="url",
        sourceRef="https://www.tiktok.com/@creator/video/1",
        status="partial",
        artifacts=[SourceArtifact(artifactType="caption", text="Hà Nội")],
        branchFailures=[SourceBranchFailure(
            branch="frame_ocr",
            error=AgentError(code="MEDIA_ANALYSIS_FAILED", message="failed"),
        )],
    )

    output = service.finalize(
        intake_id="intake-2",
        draft=ExplorerDraft(inputAdm="Hà Nội"),
        input_adm="Hà Nội",
        adm_conflict=False,
        prompt_days=None,
        coverage="usable",
        source_results=[partial],
    )

    assert output.warnings == [
        "Nguồn URL #1 (www.tiktok.com) bị lỗi nhánh OCR frame "
        "(MEDIA_ANALYSIS_FAILED)."
    ]
