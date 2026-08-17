import asyncio
import base64
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.modules.explorer.adapters.url_sources import (
    _ytdlp_extract,
    metadata_artifacts,
)
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import SourceArtifact, SourceExtractionResult
from app.shared.llm import InlineMedia, LlmClient, LlmError


_TIMING = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}[.,]\d{3})\s+-->\s+"
    r"(?P<end>\d{2}:\d{2}:\d{2}[.,]\d{3})"
)
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class TranscriptBundle:
    artifacts: list[SourceArtifact]
    metadata: dict[str, Any]
    duration_seconds: float | None
    source: str


class TranscriptText(BaseModel):
    text: str = Field(min_length=1, max_length=60_000)


def _schema(value):
    if isinstance(value, dict):
        return {key: _schema(item) for key, item in value.items() if key != "default"}
    if isinstance(value, list):
        return [_schema(item) for item in value]
    return value


class YtDlpCaptionClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 30,
        cookie_file: str | None = None,
        languages: tuple[str, ...] = ("vi.*", "vi", "en.*", "en"),
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.cookie_file = cookie_file
        self.languages = languages

    async def fetch(self, url: str, target_dir: str) -> TranscriptBundle | None:
        return await asyncio.to_thread(self._fetch_sync, url, target_dir)

    def _fetch_sync(self, url: str, target_dir: str) -> TranscriptBundle | None:
        metadata_options: dict[str, Any] = {
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": self.timeout_seconds,
            "retries": 1,
            "extractor_retries": 1,
        }
        if self.cookie_file:
            metadata_options["cookiefile"] = self.cookie_file
        try:
            metadata = _ytdlp_extract(url, metadata_options, download=False)
        except Exception as exc:
            raise ExplorerOperationError(
                "YOUTUBE_CAPTION_LOOKUP_FAILED",
                "Không kiểm tra được caption YouTube.",
                retryable=True,
            ) from exc
        language = self._select_language(metadata)
        if language is None:
            return None
        options = {
            **metadata_options,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [language],
            "subtitlesformat": "vtt",
            "outtmpl": str(Path(target_dir) / "youtube.%(ext)s"),
        }
        try:
            metadata = _ytdlp_extract(url, options, download=True)
        except Exception as exc:
            raise ExplorerOperationError(
                "YOUTUBE_CAPTION_LOOKUP_FAILED",
                "Không kiểm tra được caption YouTube.",
                retryable=True,
            ) from exc
        files = sorted(
            Path(target_dir).glob("youtube*.vtt"),
            key=lambda path: (".vi" not in path.name.casefold(), path.name),
        )
        if not files:
            return None
        artifacts = self._parse_vtt(files[0], url)
        if not artifacts:
            return None
        return TranscriptBundle(
            artifacts=artifacts,
            metadata=metadata,
            duration_seconds=self._duration(metadata),
            source="youtube_caption",
        )

    def _select_language(self, metadata: dict[str, Any]) -> str | None:
        available = {
            str(value)
            for field in ("subtitles", "automatic_captions")
            for value in (metadata.get(field) or {})
        }
        for preferred in self.languages:
            prefix = preferred.removesuffix(".*").casefold()
            exact = next(
                (item for item in available if item.casefold() == prefix), None
            )
            if exact:
                return exact
            variant = next(
                (item for item in sorted(available) if item.casefold().startswith(prefix + "-")),
                None,
            )
            if variant:
                return variant
        return None

    @classmethod
    def _parse_vtt(cls, path: Path, source_url: str) -> list[SourceArtifact]:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        cues: list[tuple[float, str]] = []
        index = 0
        while index < len(lines):
            match = _TIMING.search(lines[index])
            if not match:
                index += 1
                continue
            start = cls._seconds(match.group("start"))
            index += 1
            text_lines = []
            while index < len(lines) and lines[index].strip():
                cleaned = html.unescape(_TAG.sub("", lines[index])).strip()
                if cleaned:
                    text_lines.append(cleaned)
                index += 1
            text = " ".join(text_lines)
            if text and (not cues or text != cues[-1][1]):
                cues.append((start, text))
        return cls._group_cues(cues, source_url)

    @staticmethod
    def _group_cues(
        cues: list[tuple[float, str]], source_url: str, maximum_chars: int = 10_000
    ) -> list[SourceArtifact]:
        groups: list[SourceArtifact] = []
        texts: list[str] = []
        size = 0
        start = 0.0
        for seconds, text in cues:
            if texts and size + len(text) > maximum_chars:
                groups.append(SourceArtifact(
                    artifactType="transcript",
                    text="\n".join(texts),
                    sourceUrl=source_url,
                    sourceTimeHint=YtDlpCaptionClient._time_hint(start),
                ))
                texts, size, start = [], 0, seconds
            if not texts:
                start = seconds
            texts.append(text)
            size += len(text)
        if texts:
            groups.append(SourceArtifact(
                artifactType="transcript",
                text="\n".join(texts),
                sourceUrl=source_url,
                sourceTimeHint=YtDlpCaptionClient._time_hint(start),
            ))
        return groups

    @staticmethod
    def _seconds(value: str) -> float:
        hours, minutes, seconds = value.replace(",", ".").split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    @staticmethod
    def _time_hint(seconds: float) -> str:
        hours, remainder = divmod(round(seconds), 3600)
        minutes, second = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{second:02d}"

    @staticmethod
    def _duration(metadata: dict[str, Any]) -> float | None:
        value = metadata.get("duration")
        return float(value) if isinstance(value, (int, float)) and value >= 0 else None


class YtDlpAudioClient:
    def __init__(
        self, *, timeout_seconds: float = 30, cookie_file: str | None = None,
        max_filesize_mb: int = 500,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.cookie_file = cookie_file
        self.max_filesize_mb = max_filesize_mb

    async def download(self, url: str, target_dir: str) -> tuple[str, dict[str, Any]]:
        return await asyncio.to_thread(self._download_sync, url, target_dir)

    def _download_sync(self, url: str, target_dir: str) -> tuple[str, dict[str, Any]]:
        options: dict[str, Any] = {
            "quiet": True, "noprogress": True, "no_warnings": True,
            "noplaylist": True, "format": "bestaudio/best",
            "outtmpl": str(Path(target_dir) / "youtube-audio.%(ext)s"),
            "socket_timeout": self.timeout_seconds,
            "max_filesize": self.max_filesize_mb * 1024 * 1024,
            "retries": 1, "fragment_retries": 1, "extractor_retries": 1,
        }
        if self.cookie_file:
            options["cookiefile"] = self.cookie_file
        metadata = _ytdlp_extract(url, options, download=True)
        files = [
            path for path in Path(target_dir).glob("youtube-audio.*")
            if path.is_file() and not path.name.endswith((".part", ".ytdl"))
        ]
        if not files:
            raise ExplorerOperationError(
                "YOUTUBE_AUDIO_EMPTY", "YouTube không tạo được audio fallback."
            )
        return str(max(files, key=lambda item: item.stat().st_size)), metadata


class GeminiAudioTranscriber:
    def __init__(
        self, client: LlmClient, *, chunk_seconds: int = 300,
        overlap_seconds: int = 5, max_concurrency: int = 8,
        max_duration_seconds: int = 14_400,
    ) -> None:
        self.client = client
        self.chunk_seconds = chunk_seconds
        self.overlap_seconds = overlap_seconds
        self.max_concurrency = max_concurrency
        self.max_duration_seconds = max_duration_seconds

    async def transcribe(
        self, media_path: str, work_dir: str, source_url: str
    ) -> tuple[list[SourceArtifact], float]:
        duration = await self._duration(media_path)
        if duration > self.max_duration_seconds:
            raise ExplorerOperationError(
                "YOUTUBE_DURATION_LIMIT",
                "YouTube dài hơn giới hạn transcription đã cấu hình.",
            )
        chunks = await self._split(media_path, work_dir, duration)
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def run(path: str, start: float):
            async with semaphore:
                return start, await self._transcribe_chunk(path)

        results = await asyncio.gather(*(run(path, start) for path, start in chunks))
        return [
            SourceArtifact(
                artifactType="transcript", text=result.text,
                sourceUrl=source_url,
                sourceTimeHint=YtDlpCaptionClient._time_hint(start),
            )
            for start, result in sorted(results)
        ], duration

    async def _split(
        self, media_path: str, work_dir: str, duration: float
    ) -> list[tuple[str, float]]:
        step = max(1, self.chunk_seconds - self.overlap_seconds)
        starts = list(range(0, max(1, int(duration)), step))

        async def extract(index: int, start: int) -> tuple[str, float]:
            path = str(Path(work_dir) / f"youtube-chunk-{index:04d}.mp3")
            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-ss", str(start), "-i", media_path,
                "-t", str(self.chunk_seconds), "-vn", "-ac", "1", "-ar", "16000",
                "-b:a", "64k", path,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            if process.returncode != 0 or not Path(path).exists():
                raise ExplorerOperationError(
                    "AUDIO_EXTRACTION_FAILED", "Không chia được audio YouTube."
                )
            return path, float(start)

        return list(await asyncio.gather(*(
            extract(index, start) for index, start in enumerate(starts)
        )))

    async def _transcribe_chunk(self, path: str) -> TranscriptText:
        media = InlineMedia(
            mime_type="audio/mpeg",
            data_base64=base64.b64encode(Path(path).read_bytes()).decode(),
        )
        try:
            raw = await self.client.generate_media(
                "Transcribe this entire audio chunk faithfully. Preserve every named place, "
                "address and useful travel detail. Do not summarize.",
                [media], temperature=0.0, max_output_tokens=8000,
                response_json_schema=_schema(TranscriptText.model_json_schema()),
            )
            return TranscriptText.model_validate(json.loads(raw))
        except (LlmError, json.JSONDecodeError, ValidationError) as exc:
            raise ExplorerOperationError(
                "YOUTUBE_TRANSCRIPTION_FAILED",
                "Gemini không transcribe được một audio chunk.", retryable=True,
            ) from exc

    @staticmethod
    async def _duration(media_path: str) -> float:
        process = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", media_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            raise ExplorerOperationError(
                "MEDIA_PROBE_FAILED", "Không đọc được duration audio YouTube."
            )
        return float(stdout.decode().strip())


class YouTubeTranscriptSourceExtractor:
    def __init__(
        self,
        captions,
        audio,
        transcriber,
        *,
        max_concurrency: int = 1,
    ) -> None:
        self.captions = captions
        self.audio = audio
        self.transcriber = transcriber
        self._limiter = asyncio.Semaphore(max(1, max_concurrency))

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        async with self._limiter:
            return await self._extract(url, source_index=source_index)

    async def _extract(self, url: str, *, source_index: int):
        with TemporaryDirectory(prefix="explorer-youtube-") as work_dir:
            try:
                bundle = await self.captions.fetch(url, work_dir)
            except ExplorerOperationError:
                bundle = None
            if bundle is None:
                audio_path, metadata = await self.audio.download(url, work_dir)
                transcript, duration = await self.transcriber.transcribe(
                    audio_path, work_dir, url
                )
                artifacts = [*metadata_artifacts(metadata, url), *transcript]
            else:
                duration = bundle.duration_seconds
                artifacts = [*metadata_artifacts(bundle.metadata, url), *bundle.artifacts]
        return SourceExtractionResult(
            sourceIndex=source_index, sourceKind="url", sourceRef=url,
            status="succeeded", artifacts=artifacts,
            sourceDurationSeconds=duration,
            analyzedDurationSeconds=duration,
            coverageRatio=1.0 if duration is not None else None,
            coverageStatus="complete" if duration is not None else "unknown",
        )
