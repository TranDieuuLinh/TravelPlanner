from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from app.modules.plans.explorer.tools.url_reels.extractor import UrlReelContextExtractor
from app.modules.plans.explorer.tools.url_reels.frame_vision import (
    GeminiReelFrameVision,
)
from app.modules.plans.explorer.tools.url_reels.loader import UrlReelLoader
from app.modules.plans.explorer.tools.url_reels.media import UrlReelMediaExtractor
from app.modules.plans.explorer.tools.url_reels.schema import (
    MediaArtifacts,
    FrameVisionResult,
    SpeechToTextResult,
    UrlReelExtractionResult,
    UrlReelInput,
)
from app.modules.plans.explorer.tools.url_reels.speech_to_text import GeminiAudioSpeechToText


class UrlReelExtractionService:
    def __init__(
        self,
        loader: UrlReelLoader | None = None,
        media: UrlReelMediaExtractor | None = None,
        speech_to_text: GeminiAudioSpeechToText | None = None,
        context_extractor: UrlReelContextExtractor | None = None,
        frame_vision: GeminiReelFrameVision | None = None,
    ) -> None:
        self.loader = loader or UrlReelLoader()
        self.media = media or UrlReelMediaExtractor()
        self.speech_to_text = speech_to_text
        self.context_extractor = context_extractor or UrlReelContextExtractor()
        self.frame_vision = frame_vision

    def extract(self, payload: UrlReelInput) -> UrlReelExtractionResult:
        if payload.work_dir is not None:
            return self._extract_in_work_dir(payload, payload.work_dir)

        with TemporaryDirectory(prefix="vsf_url_reel_") as temporary_dir:
            result = self._extract_in_work_dir(payload, Path(temporary_dir))
            result.artifacts = MediaArtifacts()
            return result

    def _extract_in_work_dir(
        self,
        payload: UrlReelInput,
        work_dir: Path,
    ) -> UrlReelExtractionResult:
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

        speech_result = SpeechToTextResult(
            text="",
            status="skipped",
            durationSeconds=0.0,
        )
        vision_result = FrameVisionResult()
        start = time.perf_counter()
        stt_prompt = payload.stt_initial_prompt
        if stt_prompt is None and payload.destination:
            stt_prompt = (
                f"This is a travel itinerary video about {payload.destination}. "
                "It may mention destinations, cafes, restaurants, attractions, "
                "hotels, neighborhoods, and transport."
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            speech_future = (
                executor.submit(
                    (self.speech_to_text or GeminiAudioSpeechToText()).transcribe,
                    artifacts.audio_path,
                    language=payload.stt_language,
                    initial_prompt=stt_prompt,
                )
                if artifacts.audio_path is not None
                else None
            )
            vision_future = (
                executor.submit(
                    (self.frame_vision or GeminiReelFrameVision()).analyze,
                    artifacts.frame_paths,
                    destination=payload.destination,
                )
                if artifacts.frame_paths
                else None
            )
            if speech_future is not None:
                try:
                    speech_result = speech_future.result()
                except RuntimeError as exc:
                    timings["speechToTextFailed"] = 1.0
                    speech_result = SpeechToTextResult(
                        text="",
                        status="failed",
                        error=str(exc),
                        durationSeconds=time.perf_counter() - start,
                    )
            if vision_future is not None:
                try:
                    vision_result = vision_future.result()
                except RuntimeError as exc:
                    timings["frameVisionFailed"] = 1.0
                    vision_result = FrameVisionResult(
                        status="failed",
                        error=str(exc),
                        durationSeconds=time.perf_counter() - start,
                    )

        timings["speechToText"] = speech_result.duration_seconds
        timings["frameVision"] = vision_result.duration_seconds
        timings["extractSignalsWall"] = time.perf_counter() - start

        context_arguments = {
            "metadata": metadata,
            "transcript": speech_result.text,
            "destination": payload.destination,
        }
        if vision_result.text:
            context_arguments["visual_text"] = vision_result.text
        context = self.context_extractor.extract(**context_arguments)

        result = UrlReelExtractionResult(
            url=payload.url,
            platform=metadata.platform,
            metadata=metadata,
            artifacts=artifacts,
            needsImageUpload=artifacts.audio_path is None and not artifacts.frame_paths,
            speechToText=speech_result,
            frameVision=vision_result,
            extractedContext=context,
            timings=timings,
        )
        return result
