import asyncio
import base64
import json
import logging
import math
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import (
    MediaAnalysisResult,
    SourceArtifact,
    SourceBranch,
    SourceBranchFailure,
)
from app.shared.contracts.agent import AgentError
from app.shared.llm import InlineMedia, LlmClient, LlmError


logger = logging.getLogger(__name__)


class MediaObservation(BaseModel):
    item_index: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4000)


class MediaReadResult(BaseModel):
    observations: list[MediaObservation] = Field(default_factory=list)


def _provider_schema(value):
    if isinstance(value, dict):
        return {
            key: _provider_schema(item)
            for key, item in value.items()
            if key != "default"
        }
    if isinstance(value, list):
        return [_provider_schema(item) for item in value]
    return value


class FfmpegMediaProcessor:
    async def stream_types(self, media_path: str) -> set[str]:
        process = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
            "-of", "json", media_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode != 0:
            raise ExplorerOperationError(
                "MEDIA_PROBE_FAILED", "Không đọc được stream trong media."
            )
        try:
            value = json.loads(stdout.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExplorerOperationError(
                "MEDIA_PROBE_FAILED", "Thông tin stream media không hợp lệ."
            ) from exc
        streams = value.get("streams") if isinstance(value, dict) else None
        if not isinstance(streams, list):
            return set()
        return {
            item["codec_type"]
            for item in streams
            if isinstance(item, dict) and item.get("codec_type") in {"audio", "video"}
        }

    async def duration_seconds(self, media_path: str) -> float:
        process = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", media_path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise ExplorerOperationError(
                "MEDIA_PROBE_FAILED", "Không đọc được thời lượng media."
            )
        try:
            return float(stdout.decode().strip())
        except ValueError as exc:
            raise ExplorerOperationError(
                "MEDIA_PROBE_FAILED", "Thời lượng media không hợp lệ."
            ) from exc

    async def extract_frames(
        self,
        media_path: str,
        output_dir: str,
        *,
        interval_seconds: float,
        max_seconds: float,
        max_frames: int,
    ) -> list[str]:
        template = str(Path(output_dir) / "frame-%06d.jpg")
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-v", "error", "-i", media_path, "-t", str(max_seconds),
            "-vf", f"fps=1/{interval_seconds},scale='min(768,iw)':-2",
            "-frames:v", str(max_frames), "-q:v", "5", template,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode != 0:
            raise ExplorerOperationError(
                "FRAME_EXTRACTION_FAILED", "Không trích xuất được frame video."
            )
        return [str(path) for path in sorted(Path(output_dir).glob("frame-*.jpg"))]

    async def extract_audio_chunks(
        self,
        media_path: str,
        output_dir: str,
        *,
        duration_seconds: float,
        chunk_count: int,
    ) -> list[tuple[str, float]]:
        bounded = max(0.1, duration_seconds)
        chunk_duration = bounded / chunk_count
        jobs = []
        paths = []
        for index in range(chunk_count):
            start = index * chunk_duration
            path = str(Path(output_dir) / f"audio-{index + 1}.mp3")
            paths.append((path, start))
            jobs.append(self._extract_audio(
                media_path, path, start=start, duration=chunk_duration
            ))
        await asyncio.gather(*jobs)
        return [(path, start) for path, start in paths if Path(path).stat().st_size]

    @staticmethod
    async def _extract_audio(
        media_path: str, output_path: str, *, start: float, duration: float
    ) -> None:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-v", "error", "-ss", str(start), "-i", media_path,
            "-t", str(duration), "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", "64k", output_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        if process.returncode != 0:
            raise ExplorerOperationError(
                "AUDIO_EXTRACTION_FAILED", "Không trích xuất được audio."
            )


class GeminiMediaAnalyzer:
    def __init__(
        self,
        client: LlmClient,
        *,
        audio_client: LlmClient | None = None,
        frame_interval_seconds: float = 3,
        frame_batch_size: int = 10,
        max_frames: int = 48,
        frame_max_concurrency: int = 5,
        audio_chunk_count: int = 3,
        audio_chunk_seconds: float = 60,
        max_video_seconds: float = 180,
    ) -> None:
        self.vision_client = client
        self.audio_client = audio_client or client
        self.frame_interval_seconds = frame_interval_seconds
        self.frame_batch_size = frame_batch_size
        self.max_frames = max_frames
        self.frame_max_concurrency = frame_max_concurrency
        self.audio_chunk_count = audio_chunk_count
        self.audio_chunk_seconds = audio_chunk_seconds
        self.max_video_seconds = max_video_seconds
        self.ffmpeg = FfmpegMediaProcessor()

    async def analyze(
        self,
        media_path: str,
        work_dir: str,
        source_url: str,
        *,
        branches: set[SourceBranch] | None = None,
    ) -> MediaAnalysisResult:
        duration_value, stream_types = await asyncio.gather(
            self.ffmpeg.duration_seconds(media_path),
            self.ffmpeg.stream_types(media_path),
        )
        duration = min(duration_value, self.max_video_seconds)
        frames_dir = Path(work_dir) / "frames"
        audio_dir = Path(work_dir) / "audio"
        jobs = []
        active_branches: list[SourceBranch] = []
        requested = branches or {"frame_ocr", "stt"}
        if "video" in stream_types and "frame_ocr" in requested:
            frames_dir.mkdir()
            active_branches.append("frame_ocr")
            jobs.append(self._analyze_frames(
                media_path, str(frames_dir), source_url, duration
            ))
        if "audio" in stream_types and "stt" in requested:
            audio_dir.mkdir()
            active_branches.append("stt")
            jobs.append(self._analyze_audio(
                media_path, str(audio_dir), source_url, duration
            ))
        results = await asyncio.gather(*jobs, return_exceptions=True)
        artifacts: list[SourceArtifact] = []
        failures: list[SourceBranchFailure] = []
        for branch, result in zip(active_branches, results):
            if isinstance(result, list):
                artifacts.extend(result)
                continue
            failure = self._branch_failure(branch, result)
            failures.append(failure)
            logger.warning(
                "Explorer media branch failed: branch=%s code=%s retryable=%s",
                branch,
                failure.error.code,
                failure.error.retryable,
                exc_info=(type(result), result, result.__traceback__),
            )
        return MediaAnalysisResult(artifacts=artifacts, failures=failures)

    async def analyze_image(self, data_base64: str, mime_type: str) -> str:
        result = await self._read_media(
            "Read every visible line that contains a named place or travel detail in "
            "this image. Preserve every named place, even when it seems obvious or "
            "repeats elsewhere. Keep the text faithful; do not add facts. Return one "
            "complete observation.",
            [InlineMedia(mime_type=mime_type, data_base64=data_base64)],
            client=self.vision_client,
        )
        return "\n".join(item.text for item in result.observations)

    async def _analyze_frames(
        self, media_path: str, output_dir: str, source_url: str, duration: float
    ) -> list[SourceArtifact]:
        frames = await self.ffmpeg.extract_frames(
            media_path, output_dir,
            interval_seconds=self.frame_interval_seconds,
            max_seconds=duration,
            max_frames=self.max_frames,
        )
        groups = self._batches(frames, self.frame_batch_size)
        semaphore = asyncio.Semaphore(self.frame_max_concurrency)

        async def analyze_group(
            group: list[str], group_index: int
        ) -> MediaReadResult:
            async with semaphore:
                return await self._ocr_group(group, group_index)

        batches = await asyncio.gather(*(
            analyze_group(group, group_index)
            for group_index, group in enumerate(groups)
        ))
        artifacts = []
        for group_index, (group, result) in enumerate(zip(groups, batches)):
            group_start = sum(len(item) for item in groups[:group_index])
            for observation in result.observations:
                absolute_index = group_start + observation.item_index - 1
                if absolute_index >= len(frames):
                    continue
                seconds = absolute_index * self.frame_interval_seconds
                artifacts.append(SourceArtifact(
                    artifactType="frame_ocr", text=observation.text,
                    sourceUrl=source_url, sourceTimeHint=self._time_hint(seconds),
                ))
        return artifacts

    async def _ocr_group(
        self, frame_paths: list[str], group_index: int
    ) -> MediaReadResult:
        media = [
            InlineMedia(
                mime_type="image/jpeg",
                data_base64=base64.b64encode(Path(path).read_bytes()).decode(),
            )
            for path in frame_paths
        ]
        return await self._read_media(
            f"These are consecutive video frames in batch {group_index + 1}. "
            "For each frame that contains useful travel information, return its 1-based "
            "index and faithfully transcribe visible place names, addresses, prices, "
            "timing advice, or non-obvious travel facts. Skip logos and generic text.",
            media,
            client=self.vision_client,
        )

    async def _analyze_audio(
        self, media_path: str, output_dir: str, source_url: str, duration: float
    ) -> list[SourceArtifact]:
        chunk_count = min(
            self.audio_chunk_count,
            max(1, math.ceil(duration / self.audio_chunk_seconds)),
        )
        chunks = await self.ffmpeg.extract_audio_chunks(
            media_path, output_dir,
            duration_seconds=duration, chunk_count=chunk_count,
        )
        results = await asyncio.gather(*(
            self._stt_chunk(path, index) for index, (path, _) in enumerate(chunks)
        ))
        return [
            SourceArtifact(
                artifactType="stt", text=observation.text, sourceUrl=source_url,
                sourceTimeHint=self._time_hint(chunks[index][1]),
            )
            for index, result in enumerate(results)
            for observation in result.observations
        ]

    async def _stt_chunk(self, path: str, index: int) -> MediaReadResult:
        media = InlineMedia(
            mime_type="audio/mpeg",
            data_base64=base64.b64encode(Path(path).read_bytes()).decode(),
        )
        return await self._read_media(
            f"Transcribe audio chunk {index + 1} faithfully. Keep named places, addresses, "
            "prices, timing advice and useful travel details. Return one observation.",
            [media],
            client=self.audio_client,
        )

    async def _read_media(
        self,
        prompt: str,
        media: list[InlineMedia],
        *,
        client: LlmClient,
    ) -> MediaReadResult:
        if not media:
            return MediaReadResult()
        try:
            raw = await client.generate_media(
                prompt, media, temperature=0.0, max_output_tokens=1800,
                response_json_schema=_provider_schema(MediaReadResult.model_json_schema()),
            )
            return MediaReadResult.model_validate(json.loads(raw))
        except (LlmError, json.JSONDecodeError, ValidationError) as exc:
            raise ExplorerOperationError(
                "MEDIA_ANALYSIS_FAILED", "Gemini không đọc được media.", retryable=True
            ) from exc

    @staticmethod
    def _batches(values: list[str], maximum_size: int) -> list[list[str]]:
        if not values:
            return []
        return [
            values[start:start + maximum_size]
            for start in range(0, len(values), maximum_size)
        ]

    @staticmethod
    def _branch_failure(
        branch: SourceBranch, exc: BaseException
    ) -> SourceBranchFailure:
        if isinstance(exc, ExplorerOperationError):
            error = AgentError(
                code=exc.code,
                message=str(exc),
                retryable=exc.retryable,
            )
        else:
            error = AgentError(
                code="MEDIA_BRANCH_FAILED",
                message="Không thể phân tích một nhánh media.",
                retryable=True,
            )
        return SourceBranchFailure(branch=branch, error=error)

    @staticmethod
    def _time_hint(seconds: float) -> str:
        minutes, second = divmod(round(seconds), 60)
        return f"{minutes:02d}:{second:02d}"
