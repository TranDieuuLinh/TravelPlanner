from __future__ import annotations

from pathlib import Path
import shutil
import time
from threading import Event, Lock

import pytest
from yt_dlp.utils import DownloadError

from app.modules.plans.explorer.tools.url_reels.extractor import (
    UrlReelContextExtractor,
)
from app.modules.plans.explorer.tools.url_reels.frame_vision import (
    GeminiReelFrameVision,
)
from app.modules.plans.explorer.tools.url_reels.media import (
    UrlReelMediaExtractor,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.service import (
    UrlReelExtractionService,
)


class FakeLoader:
    def load_metadata(self, url: str) -> UrlMetadata:
        return UrlMetadata(
            originalUrl=url,
            canonicalUrl=url,
            platform="youtube",
            title="Hanoi",
        )


class FakeMedia:
    def prepare(
        self,
        url: str,
        work_dir: Path,
    ) -> tuple[MediaArtifacts, dict[str, float]]:
        video_path = work_dir / "reel.mp4"
        audio_path = work_dir / "audio.mp3"
        video_path.write_bytes(b"video")
        audio_path.write_bytes(b"audio")
        return (
            MediaArtifacts(videoPath=video_path, audioPath=audio_path),
            {"downloadVideo": 0.1, "extractAudio": 0.1},
        )


class FailingMedia:
    def prepare(
        self,
        url: str,
        work_dir: Path,
    ) -> tuple[MediaArtifacts, dict[str, float]]:
        (work_dir / "partial.mp4").write_bytes(b"partial")
        raise RuntimeError("download failed")


class FakeSpeechToText:
    def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None,
        initial_prompt: str | None,
    ) -> SpeechToTextResult:
        return SpeechToTextResult(
            text="Hoan Kiem Lake",
            status="ok",
            durationSeconds=0.1,
        )


class FakeContextExtractor:
    def extract(
        self,
        metadata: UrlMetadata,
        transcript: str,
        destination: str | None = None,
    ) -> ExtractedContext:
        return ExtractedContext(
            extractedPlaces=["Hoan Kiem Lake"],
            confidence=0.9,
        )


def build_service(media: FakeMedia | FailingMedia) -> UrlReelExtractionService:
    return UrlReelExtractionService(
        loader=FakeLoader(),
        media=media,
        speech_to_text=FakeSpeechToText(),
        context_extractor=FakeContextExtractor(),
    )


def test_automatically_removes_owned_artifacts_after_extraction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_dir = tmp_path / "vsf_url_reel_test"
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.service.TemporaryDirectory",
        lambda **_: TemporaryDirectoryStub(temporary_dir),
    )

    result = build_service(FakeMedia()).extract(
        UrlReelInput(url="https://example.com/video")
    )

    assert not temporary_dir.exists()
    assert result.artifacts == MediaArtifacts()
    assert result.speech_to_text.text == "Hoan Kiem Lake"


def test_automatically_removes_owned_artifacts_when_extraction_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary_dir = tmp_path / "vsf_url_reel_failure"
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.service.TemporaryDirectory",
        lambda **_: TemporaryDirectoryStub(temporary_dir),
    )

    with pytest.raises(RuntimeError, match="download failed"):
        build_service(FailingMedia()).extract(
            UrlReelInput(url="https://example.com/video")
        )

    assert not temporary_dir.exists()


def test_cleans_media_inside_caller_owned_work_directory(tmp_path: Path) -> None:
    work_dir = tmp_path / "debug-artifacts"

    result = build_service(FakeMedia()).extract(
        UrlReelInput(
            url="https://example.com/video",
            workDir=work_dir,
        )
    )

    assert work_dir.exists()
    assert list(work_dir.iterdir()) == []
    assert result.artifacts == MediaArtifacts()


def test_photo_url_requires_uploaded_image() -> None:
    artifacts, timings = UrlReelMediaExtractor().prepare(
        "https://www.tiktok.com/@creator/photo/123",
        Path("/tmp/unused-photo-work-dir"),
    )

    assert artifacts == MediaArtifacts()
    assert timings["mediaUnavailable"] == 1.0


def test_video_prepare_extracts_audio_and_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path = tmp_path / "video.mp4"
    audio_path = tmp_path / "audio.mp3"
    frame_paths = [tmp_path / "frame_001.jpg", tmp_path / "frame_002.jpg"]

    def fake_download(url: str, work_dir: Path) -> Path:
        video_path.write_bytes(b"video")
        return video_path

    def fake_extract_audio(
        source: Path,
        work_dir: Path,
        key: str,
    ) -> Path:
        assert source == video_path
        audio_path.write_bytes(b"audio")
        return audio_path

    def fake_extract_frames(
        source: Path,
        work_dir: Path,
        key: str,
    ) -> list[Path]:
        assert source == video_path
        for frame_path in frame_paths:
            frame_path.write_bytes(b"image")
        return frame_paths

    media = UrlReelMediaExtractor()
    monkeypatch.setattr(media, "download_video", fake_download)
    monkeypatch.setattr(media, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(media, "extract_frames", fake_extract_frames)

    artifacts, timings = media.prepare(
        "https://www.tiktok.com/@creator/video/123",
        tmp_path,
    )

    assert artifacts.video_path == video_path
    assert artifacts.audio_path == audio_path
    assert artifacts.frame_paths == frame_paths
    assert timings["sampledFrames"] == 2.0


def test_video_frame_ocr_uses_gemini_35_flash_lite() -> None:
    assert (
        GeminiReelFrameVision(api_key="test-key").model_name
        == "gemini-3.5-flash-lite"
    )


def test_frame_ocr_runs_two_batches_concurrently_and_preserves_order() -> None:
    overlap_detected = Event()
    state_lock = Lock()
    state = {"active": 0, "maximum": 0}

    class RecordingVision(GeminiReelFrameVision):
        def _analyze_batch(
            self,
            frame_paths: list[Path],
            *,
            destination: str | None,
        ) -> FrameVisionResult:
            first_frame = int(frame_paths[0].stem.rsplit("_", 1)[-1])
            with state_lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
                if state["active"] >= 2:
                    overlap_detected.set()
            try:
                if first_frame <= 17:
                    assert overlap_detected.wait(timeout=1)
                time.sleep(0.02)
                return FrameVisionResult(
                    text=f"batch-{first_frame}",
                    places=[f"Place {first_frame}"],
                    status="ok",
                    durationSeconds=0.02,
                )
            finally:
                with state_lock:
                    state["active"] -= 1

    frames = [Path(f"frame_{index:03d}.jpg") for index in range(1, 41)]

    result = RecordingVision(api_key="test-key").analyze(
        frames,
        destination="Hanoi",
    )

    assert overlap_detected.is_set()
    assert state["maximum"] == 2
    assert result.text.splitlines() == ["batch-1", "batch-17", "batch-33"]
    assert result.places == ["Place 1", "Place 17", "Place 33"]
    assert result.status == "ok"


def test_frame_ocr_retries_failed_parallel_batch_and_keeps_other_results() -> None:
    attempts: dict[int, int] = {}
    attempts_lock = Lock()

    class PartiallyFailingVision(GeminiReelFrameVision):
        def _analyze_batch(
            self,
            frame_paths: list[Path],
            *,
            destination: str | None,
        ) -> FrameVisionResult:
            first_frame = int(frame_paths[0].stem.rsplit("_", 1)[-1])
            with attempts_lock:
                attempts[first_frame] = attempts.get(first_frame, 0) + 1
            if first_frame == 17:
                raise RuntimeError("middle batch failed")
            return FrameVisionResult(
                text=f"batch-{first_frame}",
                places=[f"Place {first_frame}"],
                status="ok",
                durationSeconds=0.01,
            )

    frames = [Path(f"frame_{index:03d}.jpg") for index in range(1, 41)]

    result = PartiallyFailingVision(api_key="test-key").analyze(
        frames,
        destination="Hanoi",
    )

    assert attempts == {1: 1, 17: 2, 33: 1}
    assert result.text.splitlines() == ["batch-1", "batch-33"]
    assert result.places == ["Place 1", "Place 33"]
    assert result.status == "partial"
    assert result.error == (
        "1 frame batch(es) failed; successful OCR evidence was preserved."
    )


def test_service_combines_stt_and_frame_ocr(tmp_path: Path) -> None:
    class MediaWithFrame(FakeMedia):
        def prepare(
            self,
            url: str,
            work_dir: Path,
        ) -> tuple[MediaArtifacts, dict[str, float]]:
            artifacts, timings = super().prepare(url, work_dir)
            frame_path = work_dir / "frame.jpg"
            frame_path.write_bytes(b"frame")
            artifacts.frame_paths = [frame_path]
            return artifacts, timings

    class FakeVision:
        def analyze(
            self,
            frame_paths: list[Path],
            *,
            destination: str | None,
        ) -> FrameVisionResult:
            return FrameVisionResult(
                text="PLACE: Train Street",
                places=["Train Street"],
                status="ok",
                durationSeconds=0.1,
            )

    service = UrlReelExtractionService(
        loader=FakeLoader(),
        media=MediaWithFrame(),
        speech_to_text=FakeSpeechToText(),
        frame_vision=FakeVision(),  # type: ignore[arg-type]
    )

    result = service.extract(
        UrlReelInput(
            url="https://example.com/video",
            destination="Hanoi",
            workDir=tmp_path,
        )
    )

    assert result.speech_to_text.status == "ok"
    assert result.frame_vision.status == "ok"
    assert "Train Street" in result.extracted_context.extracted_places
    assert result.artifacts == MediaArtifacts()


def test_tiktok_video_download_retries_with_browser_impersonation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str | None] = []

    class FakeYoutubeDL:
        def __init__(self, options: dict) -> None:
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def download(self, urls: list[str]) -> None:
            impersonate = self.options.get("impersonate")
            attempts.append(str(impersonate) if impersonate else None)
            if str(impersonate) != "chrome-131:android-14":
                raise DownloadError("TikTok challenge failed")
            output = Path(
                self.options["outtmpl"].replace("%(ext)s", "mp4")
            )
            output.write_bytes(b"impersonated-video")

    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.media.YoutubeDL",
        FakeYoutubeDL,
    )

    path = UrlReelMediaExtractor().download_video(
        "https://www.tiktok.com/@creator/video/123",
        tmp_path,
    )

    assert attempts == [None, "chrome", "chrome-131:android-14"]
    assert path.read_bytes() == b"impersonated-video"


def test_frame_ocr_filters_promotional_cta_place(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        is_error = False

        def json(self) -> dict:
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": (
                                        '{"observations":[{"order":10,'
                                        '"placeName":"Invented Hotel",'
                                        '"evidence":"ĐẶT COMBO DU LỊCH, '
                                        'INBOX ĐỂ NHẬN TƯ VẤN",'
                                        '"dayNumber":0,"timeHint":"",'
                                        '"activity":""}]}'
                                    )
                                }
                            ]
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, endpoint: str, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.frame_vision.httpx.Client",
        FakeClient,
    )
    frame_path = tmp_path / "frame.jpg"
    frame_path.write_bytes(b"image")

    result = GeminiReelFrameVision(api_key="test-key").analyze(
        [frame_path],
        destination="Hanoi",
    )

    assert result.places == []
    assert result.observations == []
    assert "ĐẶT COMBO DU LỊCH" in result.text


def test_context_extractor_preserves_hanoi_reel_stop_order() -> None:
    url = "https://www.tiktok.com/@two_peas_abroad/video/7567367997032107286"
    metadata = UrlMetadata(
        originalUrl=url,
        canonicalUrl=url,
        platform="tiktok",
        title="A perfect first day in Hanoi",
        description=(
            "📍 Xoi Yen 📍 Cafe Pho Co 📍 Hoan Kiem Lake "
            "📍 Ngoc Son Temple 🧑‍🍳 Cooking Class "
            "📍 Hoa Lo Prison Relic 📍 Dong Xuan St. "
            "📍 Pho 10 Ly Quoc Su 🚂 Train Street"
        ),
    )
    transcript = (
        "First, for breakfast, head to Xoi Yen. "
        "Next, for coffee, head to Cafe Phuc Huel. "
        "Walk on Hoan Kiem Lake and visit Ngoc Son Temple. "
        "Book a cooking class just before lunch. "
        "In the afternoon, visit Hoa Lo Prison Relic or wander down "
        "Dong Xuan Street for shopping. At dinnertime, head to "
        "Pho Ten Li Quoc Su. After dinner, head for Train Street. "
        "Lastly, for nightlife, go to Beer Street."
    )

    context = UrlReelContextExtractor().extract(
        metadata=metadata,
        transcript=transcript,
        destination="Hanoi",
    )

    assert context.extracted_places == [
        "Xoi Yen",
        "Cafe Pho Co",
        "Hoan Kiem Lake",
        "Ngoc Son Temple",
        "Cooking Class",
        "Hoa Lo Prison Relic",
        "Dong Xuan St",
        "Pho 10 Ly Quoc Su",
        "Train Street",
        "Beer Street",
    ]
    assert [item.source_order for item in context.extracted_place_details] == list(
        range(1, 11)
    )
    assert context.extracted_place_details[0].source_time_hint == "breakfast"
    assert context.extracted_place_details[4].source_time_hint == "before lunch"
    assert context.extracted_place_details[8].source_time_hint == "after dinner"
    assert context.extracted_place_details[9].source_time_hint == "nightlife"


class TemporaryDirectoryStub:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> str:
        self.path.mkdir(parents=True)
        return str(self.path)

    def __exit__(self, *args: object) -> None:
        shutil.rmtree(self.path)
