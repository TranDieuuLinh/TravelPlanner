from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import SpeechToTextResult


class GeminiAudioSpeechToText:
    def __init__(self, api_key: str | None = None) -> None:
        self.model_name = settings.gemini_audio_model
        self.api_key = api_key or settings.gemini_api_key

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
        initial_prompt: str | None = None,
    ) -> SpeechToTextResult:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for URL reel audio transcription.")

        start = time.perf_counter()
        audio_bytes = audio_path.read_bytes()
        mime_type = "audio/mpeg" if audio_path.suffix.lower() == ".mp3" else "audio/wav"
        prompt_parts = [
            "Transcribe the speech in this travel reel audio accurately.",
            "Return only the transcript text.",
            "Prefer real travel place names over similar-sounding generic words.",
            "Preserve sequence words, day references, time-of-day cues, recommended activities, dishes, prices, durations, and alternatives exactly when spoken.",
        ]
        if language:
            prompt_parts.append(f"The expected speech languages are: {language}. Preserve the language that is actually spoken.")
        if initial_prompt:
            prompt_parts.append(initial_prompt)

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent"
        with httpx.Client(timeout=90) as client:
            response = client.post(
                endpoint,
                params={"key": self.api_key},
                json={
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
                    },
                },
            )
            if response.is_error:
                raise RuntimeError(f"Gemini audio transcription failed with status {response.status_code}: {response.text[:500]}")
            data = response.json()

        text = self._extract_text(data)
        return SpeechToTextResult(
            text=text,
            language=language,
            languageProbability=None,
            durationSeconds=time.perf_counter() - start,
        )

    def _extract_text(self, data: dict) -> str:
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "\n".join(str(part.get("text", "")).strip() for part in parts if part.get("text")).strip()


def preload_audio_model() -> None:
    return None
