from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError, UnsupportedError

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import MediaArtifacts
from app.modules.plans.explorer.tools.url_reels.utils import QuietYtdlpLogger, artifact_key


class UrlMediaUnavailableError(RuntimeError):
    """Raised when the reel media cannot be downloaded or prepared."""


class UrlReelMediaExtractor:
    def download_video(self, url: str, work_dir: Path) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        key = artifact_key(url)
        existing_matches = sorted(
            path
            for path in work_dir.glob(f"reel_{key}.*")
            if path.stat().st_size > 0
        )
        if existing_matches:
            return existing_matches[0]

        output_template = str(work_dir / f"reel_{key}.%(ext)s")
        base_options = {
            "format": "worst[ext=mp4]/worst",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietYtdlpLogger(),
        }
        failures: list[Exception] = []
        for options in (
            base_options,
            {
                **base_options,
                "impersonate": ImpersonateTarget.from_str("chrome"),
            },
            {
                **base_options,
                "impersonate": ImpersonateTarget.from_str(
                    "chrome-131:android-14"
                ),
            },
        ):
            try:
                with YoutubeDL(options) as ydl:
                    ydl.download([url])
                break
            except (DownloadError, UnsupportedError) as exc:
                failures.append(exc)
                for partial in work_dir.glob(f"reel_{key}.*"):
                    partial.unlink(missing_ok=True)
        else:
            raise UrlMediaUnavailableError(
                "yt-dlp failed with standard, desktop-browser, and "
                "Android-browser requests."
            ) from failures[-1]

        matches = sorted(work_dir.glob(f"reel_{key}.*"))
        if not matches:
            raise UrlMediaUnavailableError("yt-dlp did not create a video file")
        return matches[0]

    def extract_audio(self, video_path: Path, work_dir: Path, key: str) -> Path:
        audio_path = work_dir / f"audio_{key}.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-b:a",
                "48k",
                str(audio_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return audio_path

    def extract_frames(
        self,
        video_path: Path,
        work_dir: Path,
        key: str,
        *,
        maximum_frames: int | None = None,
    ) -> list[Path]:
        maximum_frames = maximum_frames or settings.url_reel_max_frames
        frame_dir = work_dir / f"frames_{key}"
        frame_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(frame_dir.glob("frame_*.jpg"))
        if existing:
            return existing[:maximum_frames]
        output_pattern = frame_dir / "frame_%03d.jpg"
        duration_seconds = self._probe_duration_seconds(video_path)
        frame_interval = max(
            settings.url_reel_min_frame_interval_seconds,
            (
                duration_seconds / maximum_frames
                if duration_seconds is not None
                else 2.0
            ),
        )
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                (
                    f"fps=1/{frame_interval:.3f},"
                    f"scale={settings.url_reel_frame_width}:-2"
                ),
                "-frames:v",
                str(maximum_frames),
                "-q:v",
                "4",
                str(output_pattern),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return sorted(frame_dir.glob("frame_*.jpg"))[:maximum_frames]

    def _probe_duration_seconds(self, video_path: Path) -> float | None:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(video_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            duration = float(result.stdout.strip())
        except (FileNotFoundError, ValueError, subprocess.CalledProcessError):
            return None
        return duration if duration > 0 else None

    def prepare(
        self,
        url: str,
        work_dir: Path,
    ) -> tuple[MediaArtifacts, dict[str, float]]:
        timings: dict[str, float] = {}
        key = artifact_key(url)

        if "/photo/" in url:
            timings["mediaUnavailable"] = 1.0
            return MediaArtifacts(), timings

        start = time.perf_counter()
        try:
            video_path = self.download_video(url, work_dir)
        except UrlMediaUnavailableError:
            timings["downloadVideo"] = time.perf_counter() - start
            timings["mediaUnavailable"] = 1.0
            return MediaArtifacts(), timings
        timings["downloadVideo"] = time.perf_counter() - start
        start = time.perf_counter()
        audio_path: Path | None = None
        frame_paths: list[Path] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            audio_future = executor.submit(
                self.extract_audio,
                video_path,
                work_dir,
                key,
            )
            frames_future = executor.submit(
                self.extract_frames,
                video_path,
                work_dir,
                key,
            )
            try:
                audio_path = audio_future.result()
            except (FileNotFoundError, subprocess.CalledProcessError):
                timings["audioUnavailable"] = 1.0
            try:
                frame_paths = frames_future.result()
            except (FileNotFoundError, subprocess.CalledProcessError):
                timings["framesUnavailable"] = 1.0
        timings["prepareSignalsWall"] = time.perf_counter() - start
        timings["sampledFrames"] = float(len(frame_paths))
        timings["audioAvailable"] = 1.0 if audio_path is not None else 0.0

        return MediaArtifacts(
            videoPath=video_path,
            audioPath=audio_path,
            framePaths=frame_paths,
        ), timings
