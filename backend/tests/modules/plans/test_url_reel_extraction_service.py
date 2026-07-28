from __future__ import annotations

from pathlib import Path

import pytest

from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
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


def test_keeps_caller_owned_work_directory_for_debugging(tmp_path: Path) -> None:
    work_dir = tmp_path / "debug-artifacts"

    result = build_service(FakeMedia()).extract(
        UrlReelInput(
            url="https://example.com/video",
            workDir=work_dir,
        )
    )

    assert work_dir.exists()
    assert result.artifacts.video_path == work_dir / "reel.mp4"
    assert result.artifacts.audio_path == work_dir / "audio.mp3"


class TemporaryDirectoryStub:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> str:
        self.path.mkdir(parents=True)
        return str(self.path)

    def __exit__(self, *args: object) -> None:
        for child in self.path.iterdir():
            child.unlink()
        self.path.rmdir()
