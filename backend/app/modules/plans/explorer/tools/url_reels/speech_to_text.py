from __future__ import annotations

import base64
import json
import time
from pathlib import Path

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


class GeminiAudioSpeechToText:
    def __init__(
        self,
        api_key: str | list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.model_name = settings.gemini_audio_model
        configured_keys = api_key or settings.gemini_api_key or ""
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
            raise RuntimeError("GEMINI_API_KEY is required for URL reel audio transcription.")

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
            for api_key in self.api_keys:
                response = client.post(
                    endpoint,
                    headers={"x-goog-api-key": api_key},
                    json=request_payload,
                )
                last_status = response.status_code
                if response.status_code in {401, 403, 429}:
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
            language=language,
            languageProbability=None,
            durationSeconds=time.perf_counter() - start,
        )

    def _extract_text(self, data: dict) -> str:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()


def preload_audio_model() -> None:
    return None
