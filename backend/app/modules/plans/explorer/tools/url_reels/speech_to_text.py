from __future__ import annotations

import base64
import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import (
    SpeechToTextObservation,
    SpeechToTextResult,
)


class _GeminiAudioOutput(BaseModel):
    transcript: str
    observations: list[SpeechToTextObservation]

    model_config = {"extra": "forbid"}


class _GeminiSttRateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_start = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_start - now)
            if delay:
                time.sleep(delay)
            started_at = time.monotonic()
            self._next_start = (
                started_at
                + settings.url_reel_gemini_stt_min_interval_seconds
            )

    def defer(self, delay_seconds: float) -> None:
        with self._lock:
            self._next_start = max(
                self._next_start,
                time.monotonic() + min(60.0, max(0.0, delay_seconds)),
            )

    def reset(self) -> None:
        with self._lock:
            self._next_start = 0.0


_gemini_stt_rate_limiter = _GeminiSttRateLimiter()


class GeminiAudioSpeechToText:
    def __init__(
        self,
        api_key: str | list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.model_name = settings.gemini_audio_model
        configured_keys = api_key or settings.gemini_stt_key_pool
        raw_keys = (
            configured_keys.split(",")
            if isinstance(configured_keys, str)
            else list(configured_keys)
        )
        self.api_keys = tuple(
            key.strip()
            for key in raw_keys
            if key.strip()
        )

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> SpeechToTextResult:
        if not self.api_keys:
            raise RuntimeError(
                "GEMINI_STT_API_KEYS or GEMINI_API_KEY is required for "
                "URL reel audio transcription."
            )

        start = time.perf_counter()
        audio_duration = self._probe_duration_seconds(audio_path)
        chunk_count = self._chunk_count(audio_duration)
        if chunk_count == 1:
            result = self._transcribe_single(
                audio_path,
                api_keys=self.api_keys,
                language=language,
                initial_prompt=initial_prompt,
            )
            return result.model_copy(
                update={
                    "duration_seconds": time.perf_counter() - start,
                    "audio_duration_seconds": audio_duration,
                    "chunk_count": 1,
                    "chunk_duration_seconds": [result.duration_seconds],
                }
            )

        try:
            with TemporaryDirectory(
                prefix="vsf_stt_chunks_",
                dir=audio_path.parent,
            ) as temporary_dir:
                chunk_paths = self._split_audio(
                    audio_path,
                    duration_seconds=audio_duration or 0.0,
                    chunk_count=chunk_count,
                    output_dir=Path(temporary_dir),
                )
                chunk_results, chunk_retry_count = self._transcribe_chunks(
                    chunk_paths,
                    language=language,
                    initial_prompt=initial_prompt,
                )
        except (FileNotFoundError, subprocess.CalledProcessError):
            result = self._transcribe_single(
                audio_path,
                api_keys=self.api_keys,
                language=language,
                initial_prompt=initial_prompt,
            )
            return result.model_copy(
                update={
                    "duration_seconds": time.perf_counter() - start,
                    "audio_duration_seconds": audio_duration,
                    "chunk_count": 1,
                    "chunk_duration_seconds": [result.duration_seconds],
                }
            )

        return self._merge_chunk_results(
            chunk_results,
            language=language,
            audio_duration_seconds=audio_duration,
            total_duration_seconds=time.perf_counter() - start,
            chunk_retry_count=chunk_retry_count,
        )

    def _chunk_count(self, audio_duration_seconds: float | None) -> int:
        if (
            audio_duration_seconds is None
            or audio_duration_seconds <= settings.url_reel_stt_chunk_seconds
            or len(self.api_keys) < 2
        ):
            return 1
        return min(
            settings.url_reel_stt_max_concurrency,
            len(self.api_keys),
            math.ceil(
                audio_duration_seconds
                / settings.url_reel_stt_chunk_seconds
            ),
        )

    def _probe_duration_seconds(self, audio_path: Path) -> float | None:
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
                    str(audio_path),
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

    def _split_audio(
        self,
        audio_path: Path,
        *,
        duration_seconds: float,
        chunk_count: int,
        output_dir: Path,
    ) -> list[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        span = duration_seconds / chunk_count
        overlap = settings.url_reel_stt_overlap_seconds
        chunk_paths: list[Path] = []
        for chunk_index in range(chunk_count):
            nominal_start = chunk_index * span
            start_seconds = max(
                0.0,
                nominal_start - (overlap if chunk_index else 0.0),
            )
            end_seconds = min(
                duration_seconds,
                (chunk_index + 1) * span,
            )
            chunk_path = output_dir / f"chunk_{chunk_index + 1:03d}.mp3"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{start_seconds:.3f}",
                    "-i",
                    str(audio_path),
                    "-t",
                    f"{end_seconds - start_seconds:.3f}",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-b:a",
                    "48k",
                    str(chunk_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            chunk_paths.append(chunk_path)
        return chunk_paths

    def _transcribe_chunks(
        self,
        chunk_paths: list[Path],
        *,
        language: str | None,
        initial_prompt: str | None,
    ) -> tuple[list[SpeechToTextResult], int]:
        assigned_keys = self.api_keys[: len(chunk_paths)]
        results: list[SpeechToTextResult | None] = [None] * len(chunk_paths)
        errors: list[RuntimeError | None] = [None] * len(chunk_paths)
        with ThreadPoolExecutor(max_workers=len(chunk_paths)) as executor:
            futures = [
                executor.submit(
                    self._transcribe_single,
                    chunk_path,
                    api_keys=(api_key,),
                    language=language,
                    initial_prompt=initial_prompt,
                    chunk_index=chunk_index,
                    chunk_count=len(chunk_paths),
                )
                for chunk_index, (chunk_path, api_key) in enumerate(
                    zip(chunk_paths, assigned_keys, strict=True),
                    start=1,
                )
            ]
            for index, future in enumerate(futures):
                try:
                    results[index] = future.result()
                except RuntimeError as exc:
                    errors[index] = exc

        # Retry failed chunks only after the concurrent wave has finished, so
        # retry rotation cannot collide with keys still leased by other chunks.
        retry_count = 0
        for index, error in enumerate(errors):
            if error is None:
                continue
            retry_count += 1
            results[index] = self._transcribe_single(
                chunk_paths[index],
                api_keys=self.api_keys,
                language=language,
                initial_prompt=initial_prompt,
                chunk_index=index + 1,
                chunk_count=len(chunk_paths),
            )
        return (
            [result for result in results if result is not None],
            retry_count,
        )

    def _transcribe_single(
        self,
        audio_path: Path,
        *,
        api_keys: tuple[str, ...],
        language: str | None,
        initial_prompt: str | None,
        chunk_index: int | None = None,
        chunk_count: int | None = None,
    ) -> SpeechToTextResult:
        start = time.perf_counter()
        audio_bytes = audio_path.read_bytes()
        mime_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        prompt_parts = [
            "Transcribe this travel reel audio and extract structured travel-stop observations.",
            "Return only JSON matching the supplied schema.",
            "Prefer real travel place names over similar-sounding generic words.",
            "Preserve sequence words, day references, time-of-day cues, recommended activities, dishes, prices, durations, and alternatives exactly when spoken.",
            "Create an observation only when the speech identifies a specific place. Keep evidence as a short verbatim span supporting that observation, not the whole transcript.",
            "Use one-based chronological order. Use null for dayNumber or durationMinutes when the audio does not state them, and empty strings for missing timeHint or activity.",
            "Set searchRegion to a city or province only when the speech explicitly assigns that stop or day trip to it; otherwise use an empty string.",
            "Confidence measures confidence in the place extraction from 0 to 1.",
        ]
        if language:
            prompt_parts.append(f"The expected speech languages are: {language}. Preserve the language that is actually spoken.")
        if initial_prompt:
            prompt_parts.append(initial_prompt)
        if chunk_index is not None and chunk_count is not None:
            prompt_parts.append(
                f"This is chronological audio chunk {chunk_index} of "
                f"{chunk_count}. Extract only evidence audible in this chunk."
            )

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        request_payload = {
            "contents": [
                {
                    "parts": [
                        {"text": "\n".join(prompt_parts)},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(audio_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
                "responseJsonSchema": {
                    "type": "object",
                    "properties": {
                        "transcript": {"type": "string"},
                        "observations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "order": {
                                        "type": "integer",
                                        "minimum": 1,
                                    },
                                    "placeName": {"type": "string"},
                                    "evidence": {"type": "string"},
                                    "dayNumber": {
                                        "anyOf": [
                                            {
                                                "type": "integer",
                                                "minimum": 1,
                                                "maximum": 30,
                                            },
                                            {"type": "null"},
                                        ]
                                    },
                                    "timeHint": {"type": "string"},
                                    "activity": {"type": "string"},
                                    "searchRegion": {"type": "string"},
                                    "durationMinutes": {
                                        "anyOf": [
                                            {
                                                "type": "integer",
                                                "minimum": 15,
                                                "maximum": 720,
                                            },
                                            {"type": "null"},
                                        ]
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "minimum": 0,
                                        "maximum": 1,
                                    },
                                },
                                "required": [
                                    "order",
                                    "placeName",
                                    "evidence",
                                    "dayNumber",
                                    "timeHint",
                                    "activity",
                                    "durationMinutes",
                                    "confidence",
                                ],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["transcript", "observations"],
                    "additionalProperties": False,
                },
            },
        }
        data: dict | None = None
        last_status: int | None = None
        with httpx.Client(timeout=90) as client:
            for api_key in api_keys:
                _gemini_stt_rate_limiter.wait()
                response = client.post(
                    endpoint,
                    headers={"x-goog-api-key": api_key},
                    json=request_payload,
                )
                last_status = response.status_code
                if response.status_code == 429:
                    _gemini_stt_rate_limiter.defer(
                        self._retry_after_seconds(response)
                    )
                    continue
                if response.status_code in {401, 403}:
                    continue
                if response.is_error:
                    raise RuntimeError(
                        "Gemini audio transcription failed with status "
                        f"{response.status_code}."
                    )
                data = response.json()
                break
        if data is None:
            raise RuntimeError(
                "Gemini audio transcription could not use any configured "
                f"API key (last status {last_status or 'unknown'})."
            )

        raw_output = self._extract_text(data)
        try:
            structured = _GeminiAudioOutput.model_validate_json(raw_output)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                "Gemini audio transcription returned invalid structured JSON."
            ) from exc
        return SpeechToTextResult(
            text=structured.transcript,
            observations=structured.observations,
            source="gemini_audio",
            language=language,
            languageProbability=None,
            durationSeconds=time.perf_counter() - start,
        )

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float:
        value = response.headers.get("Retry-After", "").strip()
        if value.endswith("s"):
            value = value[:-1]
        try:
            return min(60.0, max(0.0, float(value)))
        except ValueError:
            return max(
                1.0,
                settings.url_reel_gemini_stt_min_interval_seconds,
            )

    def _merge_chunk_results(
        self,
        results: list[SpeechToTextResult],
        *,
        language: str | None,
        audio_duration_seconds: float | None,
        total_duration_seconds: float,
        chunk_retry_count: int,
    ) -> SpeechToTextResult:
        transcripts = [
            result.text.strip()
            for result in results
            if result.text.strip()
        ]
        observations: list[SpeechToTextObservation] = []
        seen_observations: set[tuple[str, int | None]] = set()
        for result in results:
            for observation in sorted(
                result.observations,
                key=lambda item: item.order,
            ):
                key = (
                    " ".join(observation.place_name.casefold().split()),
                    observation.day_number,
                )
                if key in seen_observations:
                    continue
                seen_observations.add(key)
                observations.append(
                    observation.model_copy(
                        update={"order": len(observations) + 1}
                    )
                )
        return SpeechToTextResult(
            text="\n".join(dict.fromkeys(transcripts)),
            observations=observations,
            source="gemini_audio",
            language=language,
            languageProbability=None,
            durationSeconds=total_duration_seconds,
            audioDurationSeconds=audio_duration_seconds,
            chunkCount=len(results),
            chunkDurationSeconds=[
                result.duration_seconds for result in results
            ],
            chunkRetryCount=chunk_retry_count,
        )

    def _extract_text(self, data: dict) -> str:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()


def preload_audio_model() -> None:
    return None
