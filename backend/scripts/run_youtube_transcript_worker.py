from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.plans.explorer.tools.url_reels.youtube_transcript import (
    YouTubeTranscriptExtractor,
)


class TranscriptWorkerRequest(BaseModel):
    video_id: str = Field(alias="videoId", min_length=6, max_length=32)
    languages: list[str] = Field(default_factory=lambda: ["en", "vi"])

    model_config = {"populate_by_name": True}


class TranscriptWorkerResponse(BaseModel):
    status: str
    text: str
    language: str | None = None
    is_generated: bool | None = Field(default=None, alias="isGenerated")

    model_config = {"populate_by_name": True}


app = FastAPI(title="TravelPlanner Residential YouTube Transcript Worker")
extractor = YouTubeTranscriptExtractor()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/transcripts", response_model=TranscriptWorkerResponse)
def transcript(
    payload: TranscriptWorkerRequest,
    authorization: Annotated[str | None, Header()] = None,
) -> TranscriptWorkerResponse:
    expected_token = os.environ.get("TRANSCRIPT_WORKER_SHARED_TOKEN", "")
    provided_token = (authorization or "").removeprefix("Bearer ")
    if (
        not expected_token
        or not provided_token
        or not hmac.compare_digest(provided_token, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    result = extractor.fetch(
        f"https://www.youtube.com/watch?v={payload.video_id}",
        languages=payload.languages,
    )
    return TranscriptWorkerResponse(
        status=result.status,
        text=result.text,
        language=result.language,
    )
