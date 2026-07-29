from __future__ import annotations

import base64
import time
from pathlib import Path

import httpx

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import FrameVisionResult


class GeminiReelFrameVision:
    def __init__(self, api_key: str | None = None) -> None:
        self.model_name = settings.gemini_image_ocr_model
        self.api_key = api_key or settings.gemini_api_key

    def analyze(
        self,
        frame_paths: list[Path],
        *,
        destination: str | None,
    ) -> FrameVisionResult:
        if not frame_paths:
            return FrameVisionResult()
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is required for URL reel frame vision."
            )

        start = time.perf_counter()
        prompt = (
            "Analyze these chronological frames sampled from a travel reel. "
            "Return concise plain text in the language visible in the frames. "
            "Transcribe visible place names, addresses, prices and time hints. "
            "Also describe travel-relevant venue categories and attributes such "
            "as local, hidden gem, photogenic, quiet, crowded, budget, premium, "
            "family friendly, outdoor, nightlife, beach, culture or nature. "
            "Do not invent text or identify a place without visual evidence."
        )
        if destination:
            prompt += f" The destination context is {destination}."
        parts: list[dict] = [{"text": prompt}]
        for frame_path in frame_paths:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(
                            frame_path.read_bytes()
                        ).decode("ascii"),
                    }
                }
            )

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent"
        )
        with httpx.Client(timeout=90) as client:
            response = client.post(
                endpoint,
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {"temperature": 0.0},
                },
            )
            if response.is_error:
                raise RuntimeError(
                    "Gemini frame vision failed with status "
                    f"{response.status_code}: {response.text[:500]}"
                )
            data = response.json()
        text = "\n".join(
            str(part.get("text", "")).strip()
            for part in data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
            if part.get("text")
        ).strip()
        return FrameVisionResult(
            text=text,
            status="ok",
            durationSeconds=time.perf_counter() - start,
        )
