from __future__ import annotations

from pathlib import Path
import shutil
import time
from threading import Barrier, Event, Lock

import httpx
import pytest
from pydantic import ValidationError
from yt_dlp.utils import DownloadError

from app.core.config import Settings, settings
from app.modules.plans.explorer.tools.url_reels.extractor import (
    UrlReelContextExtractor,
)
from app.modules.plans.explorer.tools.url_reels.frame_vision import (
    GeminiReelFrameVision,
    _split_balanced_batches,
)
from app.modules.plans.explorer.tools.url_reels.media import (
    UrlReelMediaExtractor,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    FrameVisionObservation,
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextObservation,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.service import (
    UrlReelExtractionService,
)
from app.modules.plans.explorer.tools.url_reels.speech_to_text import (
    GeminiAudioSpeechToText,
    _gemini_stt_rate_limiter,
)
from app.modules.plans.explorer.tools.url_reels.utils import detect_platform


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


class UnavailableMedia:
    def prepare(
        self,
        url: str,
        work_dir: Path,
    ) -> tuple[MediaArtifacts, dict[str, float]]:
        return MediaArtifacts(), {"mediaUnavailable": 1.0}


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
            observations=[
                SpeechToTextObservation(
                    order=1,
                    placeName="Hoan Kiem Lake",
                    evidence="visit Hoan Kiem Lake",
                    dayNumber=None,
                    timeHint="",
                    activity="",
                    durationMinutes=None,
                    confidence=0.95,
                )
            ],
            status="ok",
            durationSeconds=0.1,
        )


class FakeContextExtractor:
    def extract(
        self,
        metadata: UrlMetadata,
        transcript: str,
        speech_observations: list[SpeechToTextObservation] | None = None,
        destination: str | None = None,
    ) -> ExtractedContext:
        return ExtractedContext(
            extractedPlaces=["Hoan Kiem Lake"],
            confidence=0.9,
        )


@pytest.fixture(autouse=True)
def disable_gemini_stt_pacing_in_unit_tests(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        settings,
        "url_reel_gemini_stt_min_interval_seconds",
        0.0,
    )
    _gemini_stt_rate_limiter.reset()
    yield
    _gemini_stt_rate_limiter.reset()


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


def test_metadata_places_do_not_require_image_upload_when_media_is_unavailable(
    tmp_path: Path,
) -> None:
    service = UrlReelExtractionService(
        loader=FakeLoader(),
        media=UnavailableMedia(),
        context_extractor=FakeContextExtractor(),
    )

    result = service.extract(
        UrlReelInput(
            url="https://www.tiktok.com/@creator/video/123",
            workDir=tmp_path,
        )
    )

    assert result.extracted_context.extracted_places == ["Hoan Kiem Lake"]
    assert result.needs_image_upload is False


def test_loads_metadata_and_prepares_media_concurrently(tmp_path: Path) -> None:
    rendezvous = Barrier(2, timeout=1)

    class ConcurrentLoader(FakeLoader):
        def load_metadata(self, url: str) -> UrlMetadata:
            rendezvous.wait()
            return super().load_metadata(url)

    class ConcurrentMedia(FakeMedia):
        def prepare(
            self,
            url: str,
            work_dir: Path,
        ) -> tuple[MediaArtifacts, dict[str, float]]:
            rendezvous.wait()
            return super().prepare(url, work_dir)

    service = UrlReelExtractionService(
        loader=ConcurrentLoader(),
        media=ConcurrentMedia(),
        speech_to_text=FakeSpeechToText(),
        context_extractor=FakeContextExtractor(),
    )

    result = service.extract(
        UrlReelInput(
            url="https://example.com/video?tracking=ignored",
            workDir=tmp_path,
        )
    )

    assert result.speech_to_text.status == "ok"
    assert result.timings["prepareSourceWall"] >= 0


def test_youtube_caption_skips_media_and_gemini_stt(tmp_path: Path) -> None:
    class CaptionExtractor:
        def fetch(
            self,
            url: str,
            *,
            languages: str | None,
        ) -> SpeechToTextResult:
            assert url == "https://youtu.be/abc123DEF45"
            assert languages == "en,vi"
            return SpeechToTextResult(
                text="Hoan Kiem Lake",
                source="youtube_captions",
                language="en",
                durationSeconds=0.01,
            )

    class MediaMustNotRun:
        def prepare(self, url: str, work_dir: Path):
            raise AssertionError("YouTube media should not be downloaded")

    class SpeechMustNotRun:
        def transcribe(self, *args: object, **kwargs: object):
            raise AssertionError("Gemini STT should not be called")

    service = UrlReelExtractionService(
        loader=FakeLoader(),
        media=MediaMustNotRun(),  # type: ignore[arg-type]
        speech_to_text=SpeechMustNotRun(),  # type: ignore[arg-type]
        youtube_transcript=CaptionExtractor(),  # type: ignore[arg-type]
        context_extractor=FakeContextExtractor(),
    )

    result = service.extract(
        UrlReelInput(
            url="https://youtu.be/abc123DEF45",
            workDir=tmp_path,
        )
    )

    assert result.speech_to_text.source == "youtube_captions"
    assert result.timings["mediaDownloadSkipped"] == 1.0
    assert result.needs_image_upload is False


def test_youtube_short_uses_media_stt_and_frame_vision(tmp_path: Path) -> None:
    class YouTubeShortLoader(FakeLoader):
        def load_metadata(self, url: str) -> UrlMetadata:
            metadata = super().load_metadata(url)
            return metadata.model_copy(update={"platform": "youtube_shorts"})

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

    class CaptionMustNotRun:
        def fetch(self, *args: object, **kwargs: object):
            raise AssertionError("YouTube Shorts must use the media pipeline")

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
        loader=YouTubeShortLoader(),
        media=MediaWithFrame(),
        speech_to_text=FakeSpeechToText(),
        frame_vision=FakeVision(),  # type: ignore[arg-type]
        youtube_transcript=CaptionMustNotRun(),  # type: ignore[arg-type]
    )

    result = service.extract(
        UrlReelInput(
            url="https://www.youtube.com/shorts/abc123DEF45",
            destination="Hanoi",
            workDir=tmp_path,
        )
    )

    assert result.platform == "youtube_shorts"
    assert result.speech_to_text.text == "Hoan Kiem Lake"
    assert result.frame_vision.status == "ok"
    assert "Hoan Kiem Lake" in result.extracted_context.extracted_places
    assert "Train Street" in result.extracted_context.extracted_places
    assert result.timings["downloadVideo"] == 0.1


def test_youtube_without_caption_skips_media_and_stt(
    tmp_path: Path,
) -> None:
    class MissingCaptionExtractor:
        def fetch(
            self,
            url: str,
            *,
            languages: str | None,
        ) -> SpeechToTextResult:
            return SpeechToTextResult(
                text="",
                source="youtube_captions",
                status="no_captions",
                error="youtube_no_captions",
                durationSeconds=0.01,
            )

    class MediaMustNotRun:
        def prepare(self, url: str, work_dir: Path):
            raise AssertionError("YouTube media download is disabled")

    class SpeechMustNotRun:
        def transcribe(self, *args: object, **kwargs: object):
            raise AssertionError("YouTube STT is disabled")

    service = UrlReelExtractionService(
        loader=FakeLoader(),
        media=MediaMustNotRun(),  # type: ignore[arg-type]
        speech_to_text=SpeechMustNotRun(),  # type: ignore[arg-type]
        youtube_transcript=MissingCaptionExtractor(),  # type: ignore[arg-type]
        context_extractor=FakeContextExtractor(),
    )

    result = service.extract(
        UrlReelInput(
            url="https://www.youtube.com/watch?v=abc123DEF45",
            workDir=tmp_path,
        )
    )

    assert result.speech_to_text.status == "no_captions"
    assert result.artifacts == MediaArtifacts()
    assert result.timings["youtubeTranscriptUnavailable"] == 1.0
    assert result.timings["mediaDownloadSkipped"] == 1.0


def test_youtube_ip_block_requests_transcript_without_media_or_stt(
    tmp_path: Path,
) -> None:
    class BlockedCaptionExtractor:
        def fetch(
            self,
            url: str,
            *,
            languages: str | None,
        ) -> SpeechToTextResult:
            return SpeechToTextResult(
                text="",
                source="youtube_captions",
                status="blocked",
                error="youtube_ip_blocked",
                durationSeconds=0.01,
            )

    class MediaMustNotRun:
        def prepare(self, url: str, work_dir: Path):
            raise AssertionError("IP block must not be treated as no captions")

    class SpeechMustNotRun:
        def transcribe(self, *args: object, **kwargs: object):
            raise AssertionError("YouTube STT is disabled")

    service = UrlReelExtractionService(
        loader=FakeLoader(),
        media=MediaMustNotRun(),  # type: ignore[arg-type]
        speech_to_text=SpeechMustNotRun(),  # type: ignore[arg-type]
        youtube_transcript=BlockedCaptionExtractor(),  # type: ignore[arg-type]
        context_extractor=FakeContextExtractor(),
    )

    result = service.extract(
        UrlReelInput(
            url="https://www.youtube.com/watch?v=abc123DEF45",
            workDir=tmp_path,
        )
    )

    assert result.speech_to_text.status == "blocked"
    assert result.timings["mediaDownloadSkipped"] == 1.0


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://youtu.be/abc123DEF45", "youtube"),
        ("https://www.youtube.com/watch?v=abc123DEF45", "youtube"),
        ("https://m.youtube.com/shorts/abc123DEF45", "youtube_shorts"),
        ("https://www.tiktok.com/@creator/video/123", "tiktok"),
        ("https://www.instagram.com/reel/ABC123/", "instagram"),
        ("https://www.facebook.com/reel/123", "facebook"),
        ("https://fb.watch/ABC123/", "facebook"),
    ],
)
def test_detects_url_extraction_platform(url: str, platform: str) -> None:
    assert detect_platform(url) == platform


def test_platform_detection_does_not_accept_domain_suffix_spoofing() -> None:
    assert detect_platform("https://youtube.com.attacker.example/shorts/123") == "unknown"


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


def test_video_frame_sampling_is_capped_at_one_frame_per_second(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video")
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs):
        commands.append(command)

        class Result:
            stdout = ""

        return Result()

    media = UrlReelMediaExtractor()
    monkeypatch.setattr(media, "_probe_duration_seconds", lambda _: 30.0)
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.media.subprocess.run",
        fake_run,
    )
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.media.settings."
        "url_reel_min_frame_interval_seconds",
        1.0,
    )

    media.extract_frames(
        video_path,
        tmp_path,
        "sampling",
        maximum_frames=48,
    )

    filter_argument = commands[0][commands[0].index("-vf") + 1]
    assert filter_argument.startswith("fps=1/1.000,")


def test_video_frame_ocr_uses_gemini_35_flash_lite() -> None:
    assert (
        GeminiReelFrameVision(api_key="test-key").model_name
        == "gemini-3.5-flash-lite"
    )


def test_default_gemini_pool_separates_stt_and_ocr_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_keys = ",".join(f"key-{index}" for index in range(1, 11))
    monkeypatch.setattr(settings, "gemini_api_key", shared_keys)
    monkeypatch.setattr(settings, "gemini_stt_api_keys", None)
    monkeypatch.setattr(settings, "gemini_ocr_api_keys", None)

    speech = GeminiAudioSpeechToText()
    vision = GeminiReelFrameVision()

    assert speech.api_keys == tuple(f"key-{index}" for index in range(1, 6))
    assert vision.api_keys == tuple(f"key-{index}" for index in range(6, 11))
    assert set(speech.api_keys).isdisjoint(vision.api_keys)


def test_dedicated_gemini_pools_override_shared_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "gemini_api_key", "shared-key")
    monkeypatch.setattr(settings, "gemini_stt_api_keys", "stt-1,stt-2")
    monkeypatch.setattr(settings, "gemini_ocr_api_keys", "ocr-1,ocr-2")

    assert GeminiAudioSpeechToText().api_keys == ("stt-1", "stt-2")
    assert GeminiReelFrameVision().api_keys == ("ocr-1", "ocr-2")


def test_dedicated_gemini_pools_reject_overlapping_keys() -> None:
    with pytest.raises(
        ValidationError,
        match="must use different keys",
    ):
        Settings(
            _env_file=None,
            gemini_stt_api_keys="stt-key,shared-key",
            gemini_ocr_api_keys="shared-key,ocr-key",
        )


def test_gemini_stt_fallback_has_rate_safe_defaults() -> None:
    configured = Settings(_env_file=None)

    assert configured.url_reel_stt_max_concurrency == 1
    assert configured.url_reel_gemini_stt_min_interval_seconds == 6.0


def test_long_audio_is_transcribed_in_parallel_ordered_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speech = GeminiAudioSpeechToText(
        api_key="stt-1,stt-2,stt-3,stt-4,stt-5"
    )
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    barrier = Barrier(3, timeout=2)
    used_keys: list[tuple[str, ...]] = []
    used_keys_lock = Lock()

    monkeypatch.setattr(
        speech,
        "_probe_duration_seconds",
        lambda _: 120.0,
    )
    monkeypatch.setattr(settings, "url_reel_stt_chunk_seconds", 45.0)

    def fake_split(
        source: Path,
        *,
        duration_seconds: float,
        chunk_count: int,
        output_dir: Path,
    ) -> list[Path]:
        assert source == audio_path
        assert duration_seconds == 120.0
        assert chunk_count == 3
        paths = [
            output_dir / f"chunk_{index:03d}.mp3"
            for index in range(1, 4)
        ]
        for path in paths:
            path.write_bytes(b"chunk")
        return paths

    def fake_transcribe_single(
        chunk_path: Path,
        *,
        api_keys: tuple[str, ...],
        language: str | None,
        initial_prompt: str | None,
        chunk_index: int | None = None,
        chunk_count: int | None = None,
    ) -> SpeechToTextResult:
        assert language == "vi"
        assert initial_prompt == "Hà Nội"
        assert chunk_index is not None
        assert chunk_count == 3
        with used_keys_lock:
            used_keys.append(api_keys)
        barrier.wait()
        place_name = (
            "Hồ Hoàn Kiếm"
            if chunk_index in {1, 2}
            else "Cà phê Đinh"
        )
        return SpeechToTextResult(
            text=f"transcript chunk {chunk_index}",
            observations=[
                SpeechToTextObservation(
                    order=1,
                    placeName=place_name,
                    evidence=place_name,
                    dayNumber=1,
                    confidence=0.9,
                )
            ],
            durationSeconds=float(chunk_index),
        )

    monkeypatch.setattr(speech, "_split_audio", fake_split)
    monkeypatch.setattr(
        speech,
        "_transcribe_single",
        fake_transcribe_single,
    )

    result = speech.transcribe(
        audio_path,
        language="vi",
        initial_prompt="Hà Nội",
    )

    assert set(used_keys) == {("stt-1",), ("stt-2",), ("stt-3",)}
    assert result.chunk_count == 3
    assert result.audio_duration_seconds == 120.0
    assert result.chunk_duration_seconds == [1.0, 2.0, 3.0]
    assert result.chunk_retry_count == 0
    assert result.text.splitlines() == [
        "transcript chunk 1",
        "transcript chunk 2",
        "transcript chunk 3",
    ]
    assert [
        observation.place_name
        for observation in result.observations
    ] == ["Hồ Hoàn Kiếm", "Cà phê Đinh"]
    assert [
        observation.order
        for observation in result.observations
    ] == [1, 2]


def test_audio_stt_rotates_comma_separated_api_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempted_keys: list[str] = []

    class FakeHttpClient:
        def __init__(self, *, timeout: int) -> None:
            assert timeout == 90

        def __enter__(self) -> "FakeHttpClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict,
        ) -> httpx.Response:
            api_key = headers["x-goog-api-key"]
            attempted_keys.append(api_key)
            request = httpx.Request("POST", url)
            if api_key == "invalid-key":
                return httpx.Response(401, request=request)
            return httpx.Response(
                200,
                request=request,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            '{"transcript":"Xin chào Hà Nội",'
                                            '"observations":[]}'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.speech_to_text.httpx.Client",
        FakeHttpClient,
    )
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    result = GeminiAudioSpeechToText(
        api_key=" invalid-key, valid-key "
    ).transcribe(audio_path)

    assert attempted_keys == ["invalid-key", "valid-key"]
    assert result.status == "ok"
    assert result.text == "Xin chào Hà Nội"
    assert result.observations == []


def test_audio_stt_requests_and_validates_structured_observations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_payload: dict = {}

    class FakeHttpClient:
        def __init__(self, *, timeout: int) -> None:
            assert timeout == 90

        def __enter__(self) -> "FakeHttpClient":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict,
        ) -> httpx.Response:
            captured_payload.update(json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            '{"transcript":"On day two, visit '
                                            'Cafe Dinh for egg coffee.",'
                                            '"observations":[{"order":1,'
                                            '"placeName":"Cafe Dinh",'
                                            '"evidence":"visit Cafe Dinh for '
                                            'egg coffee","dayNumber":2,'
                                            '"timeHint":"","activity":"Drink '
                                            'egg coffee","durationMinutes":null,'
                                            '"confidence":0.92}]}'
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.speech_to_text.httpx.Client",
        FakeHttpClient,
    )
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    result = GeminiAudioSpeechToText(api_key="test-key").transcribe(audio_path)

    config = captured_payload["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert set(config["responseJsonSchema"]["required"]) == {
        "transcript",
        "observations",
    }
    assert result.text == "On day two, visit Cafe Dinh for egg coffee."
    assert result.observations[0].model_dump(by_alias=True) == {
        "order": 1,
        "placeName": "Cafe Dinh",
        "evidence": "visit Cafe Dinh for egg coffee",
        "dayNumber": 2,
            "timeHint": "",
            "activity": "Drink egg coffee",
            "searchRegion": "",
            "durationMinutes": None,
        "confidence": 0.92,
    }


def test_context_extractor_merges_structured_stt_and_ocr_provenance() -> None:
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://example.com/reel",
            canonicalUrl="https://example.com/reel",
            platform="tiktok",
            title="Hanoi",
        ),
        # This deliberately conflicts with the structured result. Python must
        # not infer another candidate or day from free-form transcript text.
        transcript="On day nine, visit Wrong Place Museum.",
        speech_observations=[
            SpeechToTextObservation(
                order=1,
                placeName="Cafe Dinh",
                evidence="visit Cafe Dinh for egg coffee",
                dayNumber=2,
                timeHint="",
                activity="Drink egg coffee",
                durationMinutes=None,
                confidence=0.92,
            )
        ],
        destination="Hanoi",
        visual_places=["Cafe Dinh"],
        visual_observations=[
            FrameVisionObservation(
                order=15,
                placeName="Cafe Dinh",
                evidence="Cafe Dinh (Egg Coffee)",
            )
        ],
    )

    assert context.extracted_places == ["Cafe Dinh"]
    merged = context.extracted_place_details[0]
    assert merged.source_order == 15
    assert merged.source_day == 2
    assert merged.source_activity == "Drink egg coffee"
    assert merged.source_evidence == {
        "stt": "visit Cafe Dinh for egg coffee",
        "ocr": "Cafe Dinh (Egg Coffee)",
    }


def test_context_extractor_treats_city_duration_as_stay_not_place() -> None:
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://www.instagram.com/reel/example",
            canonicalUrl="https://www.instagram.com/reel/example",
            platform="instagram",
            title="Vietnam itinerary",
        ),
        transcript="",
        speech_observations=[],
        destination="unspecified",
        visual_text="PLACE: [unidentified] | Hanoi - 2 days",
    )

    assert context.extracted_places == []
    assert context.extracted_place_details == []
    assert [
        stay.model_dump(mode="json", by_alias=True)
        for stay in context.destination_stays
    ] == [
        {
            "name": "Hanoi",
            "durationDays": 2,
            "startDay": 1,
            "endDay": 2,
            "sourceOrder": 1,
            "evidence": "Hanoi - 2 days",
        }
    ]


def test_context_extractor_spreads_consecutive_city_stays_across_days() -> None:
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://www.instagram.com/reel/example",
            canonicalUrl="https://www.instagram.com/reel/example",
            platform="instagram",
        ),
        transcript="",
        speech_observations=[],
        destination="unspecified",
        visual_observations=[
            FrameVisionObservation(
                order=1,
                placeName="Hanoi - 2 days",
                evidence="Hanoi - 2 days",
            ),
            FrameVisionObservation(
                order=2,
                placeName="Ninh Binh - 1 day",
                evidence="Ninh Binh - 1 day",
            ),
            FrameVisionObservation(
                order=3,
                placeName="Hoi An - 1 day",
                evidence="Hoi An - 1 day",
            ),
        ],
    )

    assert context.extracted_places == []
    assert [
        (stay.name, stay.start_day, stay.end_day)
        for stay in context.destination_stays
    ] == [
        ("Hanoi", 1, 2),
        ("Ninh Binh", 3, 3),
        ("Hoi An", 4, 4),
    ]


def test_context_extractor_prioritizes_tagged_metadata_location() -> None:
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://www.tiktok.com/@creator/video/123",
            canonicalUrl="https://www.tiktok.com/@creator/video/123",
            platform="tiktok",
            title="Coffee places in Hanoi",
            raw={
                "place": "Café Đinh",
                "location_address": "13 Đinh Tiên Hoàng, Hoàn Kiếm",
                "city": "Hà Nội",
            },
        ),
        transcript="Then visit another coffee shop.",
        speech_observations=[
            SpeechToTextObservation(
                order=1,
                placeName="Another Coffee Shop",
                evidence="visit another coffee shop",
                searchRegion="",
                confidence=0.8,
            )
        ],
        destination="Hà Nội",
        visual_places=["Café Đinh Hanoi"],
    )

    assert context.extracted_places == [
        "Café Đinh",
        "Another Coffee Shop",
    ]
    tagged = context.extracted_place_details[0]
    assert tagged.source_order == 1
    assert tagged.address == "13 Đinh Tiên Hoàng, Hoàn Kiếm"
    assert tagged.search_region == "Hà Nội"
    assert tagged.source_evidence["metadata"] == "Café Đinh"


def test_context_extractor_keeps_caption_pins_canonical_for_hanoi_video() -> None:
    caption = (
        "Don't skip these 4 spots in 📍Hanoi 🇻🇳 "
        "📌 Cafe Pho Co ☕ 📌 Ethnology Museum 🛖 "
        "📌 Train Street Southern Entrance 🚂 "
        "📌 Dong Xuan St and Hang Ma St 🛍️"
    )
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://www.tiktok.com/@two_peas_abroad/video/7619325732052831510",
            canonicalUrl="https://www.tiktok.com/@two_peas_abroad/video/7619325732052831510",
            platform="tiktok",
            title=(
                "Don't skip these 4 spots in 📍Hanoi 🇻🇳 "
                "📌 Cafe Pho Co ☕ 📌 Ethnology Mus..."
            ),
            description=caption,
        ),
        transcript="",
        speech_observations=[
            SpeechToTextObservation(
                order=1,
                placeName="Cafe Pho Co",
                evidence="First is Cafe Pho Co.",
                activity="drink coffee",
                searchRegion="Hanoi",
                confidence=0.95,
            ),
            SpeechToTextObservation(
                order=2,
                placeName="Museum of Ethnology",
                evidence="Second is the Museum of Ethnology.",
                searchRegion="Hanoi",
                confidence=0.95,
            ),
            SpeechToTextObservation(
                order=3,
                placeName="Train Street",
                evidence="Train Street, specifically the south entrance.",
                searchRegion="Hanoi",
                confidence=0.95,
            ),
            SpeechToTextObservation(
                order=4,
                placeName="Dong Xuan Street",
                evidence="Lastly is Dong Xuan Street.",
                searchRegion="Hanoi",
                confidence=0.95,
            ),
            SpeechToTextObservation(
                order=5,
                placeName="Hang Ma Street",
                evidence="Hang Ma Street, especially on weekends.",
                searchRegion="Hanoi",
                confidence=0.95,
            ),
            SpeechToTextObservation(
                order=6,
                placeName="Coffee 9",
                evidence="Coffee 9",
                searchRegion="Hanoi",
                confidence=0.8,
            ),
        ],
        destination="Hanoi, Vietnam",
        visual_places=[
            "Hanoi",
            "Museum of Ethnology",
            "Southern Train Street",
        ],
        visual_observations=[
            FrameVisionObservation(
                order=1,
                placeName="Cafe Pho Co",
                evidence="11 Hàng Gai, Cafe Pho Co, hidden gem",
            ),
            FrameVisionObservation(
                order=2,
                placeName="Museum of Ethnology",
                evidence="Museum of Ethnology",
            ),
            FrameVisionObservation(
                order=3,
                placeName="Southern Train Street",
                evidence="comment link for location + train timetables",
            ),
            FrameVisionObservation(
                order=6,
                placeName="Coffee Nang",
                evidence="Coffee Nang",
            ),
        ],
    )

    assert context.extracted_places[:5] == [
        "Cafe Pho Co",
        "Ethnology Museum",
        "Train Street Southern Entrance",
        "Dong Xuan St",
        "Hang Ma St",
    ]
    assert "Hanoi" not in context.extracted_places
    assert "Museum of Ethnology" not in context.extracted_places
    assert "Southern Train Street" not in context.extracted_places
    assert "Ethnology Mus" not in context.extracted_places
    assert "Coffee 9" not in context.extracted_places
    assert "Coffee Nang" in context.extracted_places
    by_name = {
        detail.name: detail
        for detail in context.extracted_place_details
    }
    assert by_name["Cafe Pho Co"].address == "11 Hàng Gai"
    assert by_name["Ethnology Museum"].category.value == "culture"
    assert by_name["Train Street Southern Entrance"].category.value == (
        "attraction"
    )
    assert by_name["Train Street Southern Entrance"].address is None


def test_frame_ocr_balances_frames_across_batches() -> None:
    frames = [Path(f"frame_{index:03d}.jpg") for index in range(1, 26)]

    batches = _split_balanced_batches(frames, maximum_batch_size=10)

    assert [len(batch) for batch in batches] == [9, 8, 8]
    assert [frame for batch in batches for frame in batch] == frames


def test_frame_ocr_runs_five_batches_with_distinct_keys_from_pool_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.frame_vision.settings."
        "url_reel_vision_batch_size",
        10,
    )
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.frame_vision.settings."
        "url_reel_vision_max_concurrency",
        5,
    )
    overlap_detected = Event()
    state_lock = Lock()
    state = {"active": 0, "maximum": 0}
    active_keys: set[str] = set()
    batch_keys: dict[int, str] = {}

    class RecordingVision(GeminiReelFrameVision):
        def _analyze_batch(
            self,
            frame_paths: list[Path],
            *,
            destination: str | None,
            api_key: str,
        ) -> FrameVisionResult:
            first_frame = int(frame_paths[0].stem.rsplit("_", 1)[-1])
            with state_lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
                assert api_key not in active_keys
                active_keys.add(api_key)
                batch_keys[first_frame] = api_key
                if state["active"] >= 5:
                    overlap_detected.set()
            try:
                if first_frame <= 41:
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
                    active_keys.remove(api_key)

    frames = [Path(f"frame_{index:03d}.jpg") for index in range(1, 49)]

    result = RecordingVision(
        api_key=[
            "unused-key",
            "ocr-key-1",
            "ocr-key-2",
            "ocr-key-3",
            "ocr-key-4",
            "ocr-key-5",
        ]
    ).analyze(
        frames,
        destination="Hanoi",
    )

    assert overlap_detected.is_set()
    assert state["maximum"] == 5
    assert set(batch_keys.values()) == {
        "ocr-key-1",
        "ocr-key-2",
        "ocr-key-3",
        "ocr-key-4",
        "ocr-key-5",
    }
    assert result.text.splitlines() == [
        "batch-1",
        "batch-11",
        "batch-21",
        "batch-31",
        "batch-40",
    ]
    assert result.places == [
        "Place 1",
        "Place 11",
        "Place 21",
        "Place 31",
        "Place 40",
    ]
    assert result.status == "ok"


def test_frame_ocr_retries_failed_parallel_batch_and_keeps_other_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.modules.plans.explorer.tools.url_reels.frame_vision.settings."
        "url_reel_vision_batch_size",
        16,
    )
    attempts: dict[int, int] = {}
    attempts_lock = Lock()

    class PartiallyFailingVision(GeminiReelFrameVision):
        def _analyze_batch(
            self,
            frame_paths: list[Path],
            *,
            destination: str | None,
            api_key: str,
        ) -> FrameVisionResult:
            first_frame = int(frame_paths[0].stem.rsplit("_", 1)[-1])
            with attempts_lock:
                attempts[first_frame] = attempts.get(first_frame, 0) + 1
            if first_frame == 15:
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

    assert attempts == {1: 1, 15: 2, 28: 1}
    assert result.text.splitlines() == ["batch-1", "batch-28"]
    assert result.places == ["Place 1", "Place 28"]
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
    assert "Hoan Kiem Lake" in result.extracted_context.extracted_places
    assert "Train Street" in result.extracted_context.extracted_places
    assert result.artifacts == MediaArtifacts()


def test_service_backfills_destination_before_stt_and_vision(
    tmp_path: Path,
) -> None:
    observed: dict[str, str | None] = {}

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

    class RecordingSpeech(FakeSpeechToText):
        def transcribe(
            self,
            audio_path: Path,
            *,
            language: str | None,
            initial_prompt: str | None,
        ) -> SpeechToTextResult:
            observed["prompt"] = initial_prompt
            return super().transcribe(
                audio_path,
                language=language,
                initial_prompt=initial_prompt,
            )

    class RecordingVision:
        def analyze(
            self,
            frame_paths: list[Path],
            *,
            destination: str | None,
        ) -> FrameVisionResult:
            observed["visionDestination"] = destination
            return FrameVisionResult(status="ok", durationSeconds=0.1)

    service = UrlReelExtractionService(
        loader=FakeLoader(),
        media=MediaWithFrame(),
        speech_to_text=RecordingSpeech(),
        frame_vision=RecordingVision(),  # type: ignore[arg-type]
    )

    service.extract(
        UrlReelInput(
            url="https://example.com/video",
            destination="unspecified",
            workDir=tmp_path,
        )
    )

    assert observed["prompt"] is not None
    assert "Hanoi" in str(observed["prompt"])
    assert "unspecified" not in str(observed["prompt"])
    assert observed["visionDestination"] == "Hanoi"


def test_context_extractor_does_not_cap_evidenced_places() -> None:
    visual_places = [
        f"Venue {index:02d} Museum"
        for index in range(1, 61)
    ]
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://example.com/reel",
            canonicalUrl="https://example.com/reel",
            platform="tiktok",
            title="Hanoi itinerary",
        ),
        transcript=(
            "This is a 7-day itinerary. On day two, take a day tour. "
            "Finish at Spoken Only Lake."
        ),
        destination="Hanoi",
        visual_places=visual_places,
    )

    assert context.extracted_places[:60] == visual_places
    assert context.extracted_places[-1] == "Spoken Only Lake"
    assert len(context.extracted_places) == 61
    assert context.extracted_place_details[-1].source_day == 2


def test_context_extractor_uses_stt_day_to_correct_frame_ocr_day() -> None:
    places = ["Hanoi Shouten", "P. Ba Trieu", "Old Quarter"]
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://example.com/reel",
            canonicalUrl="https://example.com/reel",
            platform="tiktok",
            title="7-day Hanoi itinerary",
        ),
        transcript=(
            "On day one, I visited Hanoi Shoten. "
            "I went around a nearby shopping street. "
            "At night I explored Old Quarter. "
            "On day two, I visited Trang An."
        ),
        destination="Hanoi",
        visual_places=places,
        visual_observations=[
            FrameVisionObservation(
                placeName=place,
                evidence=place,
                dayNumber=7,
            )
            for place in places
        ],
    )

    assert [
        detail.source_day
        for detail in context.extracted_place_details[:3]
    ] == [1, 1, 1]


def test_context_extractor_assigns_day_trip_search_region_and_evidence() -> None:
    context = UrlReelContextExtractor().extract(
        metadata=UrlMetadata(
            originalUrl="https://example.com/reel",
            canonicalUrl="https://example.com/reel",
            platform="tiktok",
            title="7-day Hanoi itinerary",
        ),
        transcript=(
            "On day one, I took a night bus tour to see the famous Hanoi spots. "
            "I explored Old Quarter. "
            "On day two, we went on a nature trip to Ninh Binh, "
            "just a day tour. "
            "We visited Hang Mua and Trang An. "
            "On day three, we returned to Hanoi. "
            "On day six, I went to Cem Studio."
        ),
        destination="Hanoi",
        visual_text=(
            "PLACE: Hang Mua | DAY 2\n"
            "PLACE: Trang An | DAY 2"
        ),
        visual_places=["Old Quarter", "Hang Mua", "Trang An", "Cem Studio"],
        visual_observations=[
            FrameVisionObservation(
                placeName="Hang Mua",
                evidence="PLACE: Hang Mua | DAY 2",
                dayNumber=2,
            ),
            FrameVisionObservation(
                placeName="Trang An",
                evidence="PLACE: Trang An | DAY 2",
                dayNumber=2,
            ),
        ],
    )

    by_name = {
        detail.name: detail
        for detail in context.extracted_place_details
    }
    assert by_name["Old Quarter"].search_region == "Hanoi"
    assert by_name["Hang Mua"].search_region == "Ninh Binh"
    assert by_name["Trang An"].search_region == "Ninh Binh"
    assert by_name["Cem Studio"].search_region == "Hanoi"
    assert "stt" in by_name["Hang Mua"].source_evidence
    assert "ocr" in by_name["Hang Mua"].source_evidence


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


def test_context_extractor_splits_pin_list_and_does_not_copy_caption_as_activity() -> None:
    url = "https://example.com/hanoi-reel"
    caption = (
        "Don't skip these 4 spots in 📍Hanoi 🇻🇳 "
        "📌 Cafe Pho Co ☕ 📌 Ethnology Museum 🛖 "
        "📌 Train Street Southern Entrance 🚂 "
        "📌 Dong Xuan St and Hang Ma St 🛍️ "
        "For our Train Street guide, tap the link in bio."
    )
    metadata = UrlMetadata(
        originalUrl=url,
        canonicalUrl=url,
        platform="tiktok",
        title="Four places in Hanoi",
        description=caption,
    )

    context = UrlReelContextExtractor().extract(
        metadata=metadata,
        transcript="",
        destination="unspecified",
    )

    assert context.extracted_places == [
        "Cafe Pho Co",
        "Ethnology Museum",
        "Train Street Southern Entrance",
        "Dong Xuan St",
        "Hang Ma St",
    ]
    assert all(
        detail.source_activity is None
        for detail in context.extracted_place_details
    )
    assert all(
        "Don't skip" not in detail.name
        for detail in context.extracted_place_details
    )


def test_context_extractor_parses_numbered_tiktok_caption_without_list_noise() -> None:
    url = "https://www.tiktok.com/@tereveling_/video/7667982507035348244"
    caption = (
        "10 things to do when you are in Hanoi 🇻🇳 "
        "1. Hanoi Train Street 2. St. Joseph’s Cathedral 3. Giang Cafe "
        "4. Hanoi Old Quarter 5. Visit Cute Cafes in Hanoi "
        "6. Ho Chi Minh Mausoleum 7. Tran Quoc Pagoda "
        "8. Shopping at Ba Trieu Street 9. Hoa Lo Prison "
        "10. GO! Supermarket/Lotte Mart Stay tune for more. "
        "Hanoi is really fun to explore. #hanoi #vietnam"
    )
    metadata = UrlMetadata(
        originalUrl=url,
        canonicalUrl=url,
        platform="tiktok",
        title="10 things to do when you are in Hanoi",
        description=caption,
    )

    context = UrlReelContextExtractor().extract(
        metadata=metadata,
        transcript="",
        destination="unspecified",
    )

    assert context.extracted_places == [
        "Hanoi Train Street",
        "St. Joseph’s Cathedral",
        "Giang Cafe",
        "Hanoi Old Quarter",
        "Ho Chi Minh Mausoleum",
        "Tran Quoc Pagoda",
        "Ba Trieu Street",
        "Hoa Lo Prison",
        "GO! Supermarket",
        "Lotte Mart",
    ]
    assert [
        detail.source_order for detail in context.extracted_place_details
    ] == list(range(1, 11))
    assert all(
        detail.source_evidence.get("caption")
        for detail in context.extracted_place_details
    )
    assert not any(
        "stay tune" in detail.name.casefold()
        for detail in context.extracted_place_details
    )
    assert {
        detail.search_region for detail in context.extracted_place_details
    } == {"Hanoi"}


def test_context_extractor_rejects_unsupported_ocr_logos() -> None:
    metadata = UrlMetadata(
        originalUrl="https://example.com/hanoi-cafes",
        canonicalUrl="https://example.com/hanoi-cafes",
        platform="tiktok",
        title="Cute cafes in Hanoi",
    )

    context = UrlReelContextExtractor().extract(
        metadata=metadata,
        transcript="",
        destination="unspecified",
        visual_observations=[
            FrameVisionObservation(
                order=1,
                placeName="SALTPFE",
                evidence="Visit cute cafes depending on the cafe",
                activity="Visit cute cafes",
            ),
            FrameVisionObservation(
                order=2,
                placeName="Cafe Giảng",
                evidence="Try egg coffee at Cafe Giảng",
                activity="Try egg coffee",
            ),
        ],
    )

    assert context.extracted_places == ["Cafe Giảng"]
    assert context.extracted_place_details[0].search_region == "Hanoi"
    assert context.extracted_place_details[0].confidence == 0.72


def test_context_extractor_preserves_numbered_youtube_list_and_splits_stops() -> None:
    url = "https://www.youtube.com/watch?v=example"
    transcript = (
        "Number one is Huen Kim Lake and Non Temple. "
        "Number two is Beer Street. Number three is to eat on the street. "
        "Number four is St. Joseph Cathedral. Number five is Tranquac Pagota. "
        "Number six is Halo prison. Number seven is Tang Long Water Puppet Theater. "
        "Number eight is Ho Chi Min Mausoleum / Badin Square / 1pillar Pagota. "
        "Number nine is Train Street. Number ten is Ninben."
    )
    metadata = UrlMetadata(
        originalUrl=url,
        canonicalUrl=url,
        platform="youtube",
        title="Top 10 things to do",
    )

    context = UrlReelContextExtractor().extract(
        metadata=metadata,
        transcript=transcript,
        destination="Hanoi",
    )

    # The source has ten numbered activities, but item three is not a named
    # place and items one/eight contain several independently resolvable stops.
    assert context.extracted_places == [
        "Huen Kim Lake",
        "Non Temple",
        "Beer Street",
        "St Joseph Cathedral",
        "Tranquac Pagota",
        "Halo prison",
        "Tang Long Water Puppet Theater",
        "Ho Chi Min Mausoleum",
        "Badin Square",
        "1pillar Pagota",
        "Train Street",
        "Ninben",
    ]
    assert [item.source_order for item in context.extracted_place_details] == list(
        range(1, 13)
    )
    by_name = {
        item.name: item
        for item in context.extracted_place_details
    }
    assert by_name["Tranquac Pagota"].category.value == "culture"


class TemporaryDirectoryStub:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> str:
        self.path.mkdir(parents=True)
        return str(self.path)

    def __exit__(self, *args: object) -> None:
        shutil.rmtree(self.path)
