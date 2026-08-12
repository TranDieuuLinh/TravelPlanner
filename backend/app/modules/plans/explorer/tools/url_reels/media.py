from __future__ import annotations

import html as html_lib
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from curl_cffi import requests as curl_requests
from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget
from yt_dlp.utils import DownloadError, UnsupportedError, YoutubeDLError

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import MediaArtifacts
from app.modules.plans.explorer.tools.url_reels.utils import QuietYtdlpLogger, artifact_key


class UrlMediaUnavailableError(RuntimeError):
    """Raised when the reel media cannot be downloaded or prepared."""


_TIKTOK_PLAY_URL_KEYS = {"playAddr", "play_addr"}
_TIKTOK_SCRIPT_RE = re.compile(
    r"<script[^>]*>(?P<body>.*?)</script>",
    flags=re.IGNORECASE | re.DOTALL,
)


def _walk_json_for_play_addr(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _TIKTOK_PLAY_URL_KEYS and isinstance(child, str):
                if child.startswith(("http://", "https://")):
                    return html_lib.unescape(child)
            found = _walk_json_for_play_addr(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _walk_json_for_play_addr(child)
            if found:
                return found
    return None


def _extract_tiktok_play_addr(document: str) -> str | None:
    """Read the first normalized playAddr from TikTok's embedded JSON."""
    for match in _TIKTOK_SCRIPT_RE.finditer(document):
        body = html_lib.unescape(match.group("body")).strip()
        if not body or body[0] not in "[{":
            continue
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        found = _walk_json_for_play_addr(payload)
        if found:
            return found

    # Some TikTok responses place the JSON in an escaped script string rather
    # than a standalone JSON script element.
    escaped = re.search(
        r"(?:playAddr|play_addr)\\?['\"]\s*:\s*\\?['\"](?P<url>https?://[^'\"\\]+)",
        document,
        flags=re.IGNORECASE,
    )
    return html_lib.unescape(escaped.group("url")) if escaped else None


class UrlReelMediaExtractor:
    def _download_tiktok_from_embedded_json(self, url: str, work_dir: Path) -> Path:
        key = artifact_key(url)
        output_path = work_dir / f"reel_{key}.mp4"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.tiktok.com/",
        }
        failures: list[Exception] = []
        # TikTok can return a small anti-bot shell for one TLS fingerprint and
        # the full rehydration document for another. Keep this direct HTML/CDN
        # path bounded, then let the caller fall back to yt-dlp.
        for impersonate in ("safari", "chrome", "chrome131", "safari"):
            session = curl_requests.Session(impersonate=impersonate)
            try:
                page = session.get(
                    url,
                    headers=headers,
                    timeout=settings.url_reel_network_timeout_seconds,
                    allow_redirects=True,
                )
                page.raise_for_status()
                play_addr = _extract_tiktok_play_addr(page.text)
                if not play_addr:
                    raise UrlMediaUnavailableError(
                        f"TikTok HTML ({impersonate}) did not contain playAddr"
                    )
                media = session.get(
                    play_addr,
                    headers={
                        **headers,
                        "Accept": "video/mp4,video/*;q=0.9,*/*;q=0.8",
                    },
                    timeout=settings.url_reel_network_timeout_seconds,
                    stream=True,
                )
                media.raise_for_status()
                with output_path.open("wb") as handle:
                    for chunk in media.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            handle.write(chunk)
                if output_path.stat().st_size == 0:
                    raise UrlMediaUnavailableError("TikTok CDN returned an empty video")
                return output_path
            except (OSError, ValueError, UrlMediaUnavailableError, curl_requests.errors.RequestsError) as exc:
                failures.append(exc)
                output_path.unlink(missing_ok=True)
            finally:
                session.close()
        raise UrlMediaUnavailableError(
            "TikTok embedded playAddr download failed after browser-profile retries"
        ) from failures[-1]

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

        if "tiktok.com" in url.casefold():
            try:
                return self._download_tiktok_from_embedded_json(url, work_dir)
            except UrlMediaUnavailableError:
                # Keep yt-dlp as a direct-request fallback for pages that do
                # not expose playAddr in their server-rendered HTML.
                pass

        output_template = str(work_dir / f"reel_{key}.%(ext)s")
        base_options = {
            "format": "worst[ext=mp4]/worst",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietYtdlpLogger(),
            "socket_timeout": settings.url_reel_network_timeout_seconds,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_retries": 1,
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
            except (DownloadError, UnsupportedError, YoutubeDLError) as exc:
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
            timeout=settings.url_reel_subprocess_timeout_seconds,
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
            timeout=settings.url_reel_subprocess_timeout_seconds,
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
                timeout=settings.url_reel_subprocess_timeout_seconds,
            )
            duration = float(result.stdout.strip())
        except (
            FileNotFoundError,
            ValueError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
        ):
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
            except (
                FileNotFoundError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ):
                timings["audioUnavailable"] = 1.0
            try:
                frame_paths = frames_future.result()
            except (
                FileNotFoundError,
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
            ):
                timings["framesUnavailable"] = 1.0
        timings["prepareSignalsWall"] = time.perf_counter() - start
        timings["sampledFrames"] = float(len(frame_paths))
        timings["audioAvailable"] = 1.0 if audio_path is not None else 0.0

        return MediaArtifacts(
            videoPath=video_path,
            audioPath=audio_path,
            framePaths=frame_paths,
        ), timings
