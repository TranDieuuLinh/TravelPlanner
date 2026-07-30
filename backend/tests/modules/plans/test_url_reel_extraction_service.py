from __future__ import annotations

from pathlib import Path
import shutil
import time
from threading import Barrier, Event, Lock

import httpx
import pytest
from yt_dlp.utils import DownloadError

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
        destination="Hanoi",
    )

    assert context.extracted_places == [
        "Cafe Pho Co",
        "Ethnology Museum",
        "Train Street Southern Entrance",
        "Dong Xuan St and Hang Ma St",
    ]
    assert all(
        detail.source_activity is None
        for detail in context.extracted_place_details
    )
    assert all(
        "Don't skip" not in detail.name
        for detail in context.extracted_place_details
    )


class TemporaryDirectoryStub:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> str:
        self.path.mkdir(parents=True)
        return str(self.path)

    def __exit__(self, *args: object) -> None:
        shutil.rmtree(self.path)
