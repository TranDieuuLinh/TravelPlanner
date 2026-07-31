from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.modules.plans.explorer.tools.url_reels.extractor import UrlReelContextExtractor
from app.modules.plans.explorer.tools.url_reels.frame_vision import (
    GeminiReelFrameVision,
)
from app.modules.plans.explorer.tools.url_reels.loader import UrlReelLoader
from app.modules.plans.explorer.tools.url_reels.media import UrlReelMediaExtractor
from app.modules.plans.explorer.tools.url_reels.schema import (
    FrameVisionResult,
    MediaArtifacts,
    SpeechToTextResult,
    UrlReelExtractionResult,
    UrlReelInput,
    UrlMetadata,
)
from app.modules.plans.explorer.tools.url_reels.speech_to_text import GeminiAudioSpeechToText
from app.modules.plans.explorer.tools.url_reels.utils import (
    canonicalize_url,
    detect_platform,
)
from app.modules.plans.explorer.tools.url_reels.youtube_transcript import (
    YouTubeTranscriptExtractor,
)


class UrlReelExtractionService:
    def __init__(
        self,
        loader: UrlReelLoader | None = None,
        media: UrlReelMediaExtractor | None = None,
        speech_to_text: GeminiAudioSpeechToText | None = None,
        context_extractor: UrlReelContextExtractor | None = None,
        frame_vision: GeminiReelFrameVision | None = None,
        youtube_transcript: YouTubeTranscriptExtractor | None = None,
    ) -> None:
        self.loader = loader or UrlReelLoader()
        self.media = media or UrlReelMediaExtractor()
        self.speech_to_text = speech_to_text
        self.context_extractor = context_extractor or UrlReelContextExtractor()
        self.frame_vision = frame_vision
        self.youtube_transcript = (
            youtube_transcript or YouTubeTranscriptExtractor()
        )

    def extract(self, payload: UrlReelInput) -> UrlReelExtractionResult:
        temporary_parent = payload.work_dir
        if temporary_parent is not None:
            temporary_parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix="vsf_url_reel_",
            dir=temporary_parent,
        ) as temporary_dir:
            result = self._extract_in_work_dir(payload, Path(temporary_dir))
            result.artifacts = MediaArtifacts()
            return result

    def _extract_in_work_dir(
        self,
        payload: UrlReelInput,
        work_dir: Path,
    ) -> UrlReelExtractionResult:
        extraction_start = time.perf_counter()
        work_dir.mkdir(parents=True, exist_ok=True)
        timings: dict[str, float] = {}

        source_start = time.perf_counter()

        def load_metadata() -> tuple[UrlMetadata, float]:
            start = time.perf_counter()
            metadata_result = self.loader.load_metadata(payload.url)
            return metadata_result, time.perf_counter() - start

        caption_result: SpeechToTextResult | None = None
        if detect_platform(payload.url) == "youtube":
            with ThreadPoolExecutor(max_workers=2) as executor:
                metadata_future = executor.submit(load_metadata)
                transcript_future = executor.submit(
                    self.youtube_transcript.fetch,
                    payload.url,
                    languages=payload.stt_language,
                )
                metadata, metadata_duration = metadata_future.result()
                caption_result = transcript_future.result()
            if caption_result is None:
                artifacts, media_timings = self.media.prepare(
                    canonicalize_url(payload.url),
                    work_dir=work_dir,
                )
                media_timings["youtubeTranscriptFallback"] = 1.0
            else:
                artifacts = MediaArtifacts()
                media_timings = {
                    "youtubeTranscriptAvailable": 1.0,
                    "mediaDownloadSkipped": 1.0,
                }
        else:
            with ThreadPoolExecutor(max_workers=2) as executor:
                metadata_future = executor.submit(load_metadata)
                media_future = executor.submit(
                    self.media.prepare,
                    canonicalize_url(payload.url),
                    work_dir=work_dir,
                )
                metadata, metadata_duration = metadata_future.result()
                artifacts, media_timings = media_future.result()

        timings["loadMetadata"] = metadata_duration
        timings["prepareSourceWall"] = time.perf_counter() - source_start
        timings.update(media_timings)

        speech_result = caption_result or SpeechToTextResult(
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
                if caption_result is None and artifacts.audio_path is not None
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
                except (RuntimeError, httpx.HTTPError) as exc:
                    timings["frameVisionFailed"] = 1.0
                    vision_result = FrameVisionResult(
                        status="failed",
                        error=str(exc),
                        durationSeconds=time.perf_counter() - start,
                    )

        timings["speechToText"] = speech_result.duration_seconds
        timings["sttChunkCount"] = float(speech_result.chunk_count)
        timings["sttChunkRetryCount"] = float(
            speech_result.chunk_retry_count
        )
        if speech_result.audio_duration_seconds is not None:
            timings["sttAudioDuration"] = (
                speech_result.audio_duration_seconds
            )
        if speech_result.chunk_duration_seconds:
            timings["sttSlowestChunk"] = max(
                speech_result.chunk_duration_seconds
            )
        timings["frameVision"] = vision_result.duration_seconds
        timings["extractSignalsWall"] = time.perf_counter() - start

        context_arguments = {
            "metadata": metadata,
            "transcript": speech_result.text,
            "speech_observations": speech_result.observations,
            "destination": payload.destination,
        }
        if vision_result.text:
            context_arguments["visual_text"] = vision_result.text
        if vision_result.places:
            context_arguments["visual_places"] = vision_result.places
        if vision_result.observations:
            context_arguments["visual_observations"] = (
                vision_result.observations
            )
        context_start = time.perf_counter()
        context = self.context_extractor.extract(**context_arguments)
        timings["contextExtraction"] = (
            time.perf_counter() - context_start
        )
        timings["totalExtraction"] = (
            time.perf_counter() - extraction_start
        )

        result = UrlReelExtractionResult(
            url=payload.url,
            platform=metadata.platform,
            metadata=metadata,
            artifacts=artifacts,
            needsImageUpload=(
                not speech_result.text
                and artifacts.audio_path is None
                and not artifacts.frame_paths
            ),
            speechToText=speech_result,
            frameVision=vision_result,
            extractedContext=context,
            timings=timings,
        )
        return result
