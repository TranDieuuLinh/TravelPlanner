from __future__ import annotations

import tempfile
import time
from pathlib import Path

from app.modules.plans.explorer.tools.url_reels.extractor import UrlReelContextExtractor
from app.modules.plans.explorer.tools.url_reels.loader import UrlReelLoader
from app.modules.plans.explorer.tools.url_reels.media import UrlReelMediaExtractor
from app.modules.plans.explorer.tools.url_reels.schema import SpeechToTextResult, UrlReelExtractionResult, UrlReelInput
from app.modules.plans.explorer.tools.url_reels.speech_to_text import GeminiAudioSpeechToText


class UrlReelExtractionService:
    def __init__(
        self,
        loader: UrlReelLoader | None = None,
        media: UrlReelMediaExtractor | None = None,
        speech_to_text: GeminiAudioSpeechToText | None = None,
        context_extractor: UrlReelContextExtractor | None = None,
    ) -> None:
        self.loader = loader or UrlReelLoader()
        self.media = media or UrlReelMediaExtractor()
        self.speech_to_text = speech_to_text
        self.context_extractor = context_extractor or UrlReelContextExtractor()

    def extract(self, payload: UrlReelInput) -> UrlReelExtractionResult:
        work_dir = payload.work_dir or Path(tempfile.mkdtemp(prefix="vsf_url_reel_"))
        work_dir.mkdir(parents=True, exist_ok=True)
        timings: dict[str, float] = {}

        start = time.perf_counter()
        metadata = self.loader.load_metadata(payload.url)
        timings["loadMetadata"] = time.perf_counter() - start

        artifacts, media_timings = self.media.prepare(
            metadata.canonical_url,
            work_dir=work_dir,
        )
        timings.update(media_timings)

        speech_result = SpeechToTextResult(text="", status="skipped", durationSeconds=0.0)
        start = time.perf_counter()
        if artifacts.audio_path is not None:
            stt = self.speech_to_text or GeminiAudioSpeechToText()
            stt_prompt = payload.stt_initial_prompt
            if stt_prompt is None and payload.destination:
                stt_prompt = (
                    f"This is a travel itinerary video about {payload.destination}. "
                    "It may mention destinations, cafes, restaurants, attractions, hotels, neighborhoods, and transport."
                )
            try:
                speech_result = stt.transcribe(
                    artifacts.audio_path,
                    language=payload.stt_language,
                    initial_prompt=stt_prompt,
                )
            except RuntimeError as exc:
                timings["speechToTextFailed"] = 1.0
                speech_result = SpeechToTextResult(text="", status="failed", error=str(exc), durationSeconds=time.perf_counter() - start)

        timings["speechToText"] = speech_result.duration_seconds
        timings["extractSignalsWall"] = time.perf_counter() - start

        context = self.context_extractor.extract(
            metadata=metadata,
            transcript=speech_result.text,
            destination=payload.destination,
        )

        result = UrlReelExtractionResult(
            url=payload.url,
            platform=metadata.platform,
            metadata=metadata,
            artifacts=artifacts,
            needsImageUpload=artifacts.audio_path is None and not artifacts.frame_paths,
            speechToText=speech_result,
            extractedContext=context,
            timings=timings,
        )
        return result
