from __future__ import annotations

import subprocess
import time
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError, UnsupportedError

from app.modules.plans.explorer.tools.url_reels.schema import MediaArtifacts
from app.modules.plans.explorer.tools.url_reels.utils import QuietYtdlpLogger, artifact_key


class UrlMediaUnavailableError(RuntimeError):
    """Raised when the reel media cannot be downloaded or prepared."""


class UrlReelMediaExtractor:
    def download_video(self, url: str, work_dir: Path) -> Path:
        work_dir.mkdir(parents=True, exist_ok=True)
        key = artifact_key(url)
        existing_matches = sorted(path for path in work_dir.glob(f"reel_{key}.*") if path.stat().st_size > 0)
        if existing_matches:
            return existing_matches[0]

        output_template = str(work_dir / f"reel_{key}.%(ext)s")
        options = {
            "format": "worst[ext=mp4]/worst",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietYtdlpLogger(),
        }
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])
        except (DownloadError, UnsupportedError) as exc:
            raise UrlMediaUnavailableError(str(exc)) from exc

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

    def prepare(
        self,
        url: str,
        work_dir: Path,
    ) -> tuple[MediaArtifacts, dict[str, float]]:
        timings: dict[str, float] = {}

        start = time.perf_counter()
        try:
            video_path = self.download_video(url, work_dir)
        except UrlMediaUnavailableError:
            timings["downloadVideo"] = time.perf_counter() - start
            timings["mediaUnavailable"] = 1.0
            return MediaArtifacts(), timings
        timings["downloadVideo"] = time.perf_counter() - start
        key = artifact_key(url)

        start = time.perf_counter()
        try:
            audio_path = self.extract_audio(video_path, work_dir, key)
        except (FileNotFoundError, subprocess.CalledProcessError):
            timings["extractAudio"] = time.perf_counter() - start
            timings["audioUnavailable"] = 1.0
            return MediaArtifacts(videoPath=video_path, framePaths=[]), timings
        timings["extractAudio"] = time.perf_counter() - start
        timings["prepareSignalsWall"] = timings["extractAudio"]

        return MediaArtifacts(videoPath=video_path, audioPath=audio_path, framePaths=[]), timings
