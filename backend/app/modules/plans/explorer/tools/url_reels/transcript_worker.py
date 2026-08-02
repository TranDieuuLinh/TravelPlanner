from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.modules.plans.explorer.tools.url_reels.schema import SpeechToTextResult


class YouTubeTranscriptWorker(Protocol):
    def fetch(
        self,
        video_id: str,
        *,
        languages: list[str],
    ) -> SpeechToTextResult | None: ...


class _WorkerResponse(BaseModel):
    status: str
    text: str = ""
    language: str | None = None
    is_generated: bool | None = Field(default=None, alias="isGenerated")

    model_config = {"populate_by_name": True}


class HttpYouTubeTranscriptWorker:
    """Calls an operator-owned residential worker without forwarding user data."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        video_id: str,
        *,
        languages: list[str],
    ) -> SpeechToTextResult | None:
        try:
            response = httpx.post(
                f"{self.base_url}/transcripts",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"videoId": video_id, "languages": languages},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = _WorkerResponse.model_validate(response.json())
        except (httpx.HTTPError, ValidationError, ValueError, TypeError):
            return None
        return SpeechToTextResult(
            text=payload.text,
            source="youtube_captions_residential_worker",
            language=payload.language,
            status=payload.status,
            durationSeconds=0.0,
        )
