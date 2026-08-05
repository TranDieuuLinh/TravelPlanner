from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.modules.plans.explorer.tools.url_reels.caption_structurer import (
    CaptionStructurer,
)
from app.modules.plans.destination_inference import (
    infer_destination_from_text,
    usable_destination,
)
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
from app.modules.plans.explorer.tools.web_page.service import (
    WebPageExtractionService,
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
        caption_structurer: CaptionStructurer | None = None,
        web_page: WebPageExtractionService | None = None,
    ) -> None:
        self.loader = loader or UrlReelLoader()
        self.media = media or UrlReelMediaExtractor()
        self.speech_to_text = speech_to_text
        self.context_extractor = context_extractor or UrlReelContextExtractor()
        self.frame_vision = frame_vision
        self.youtube_transcript = (
            youtube_transcript or YouTubeTranscriptExtractor()
        )
        self.caption_structurer = caption_structurer
        self.web_page = web_page or (
            WebPageExtractionService(text_structurer=caption_structurer)
            if caption_structurer is not None
            else None
        )

    def extract(self, payload: UrlReelInput) -> UrlReelExtractionResult:
        if detect_platform(payload.url) == "unknown" and self.web_page is not None:
            return self.web_page.extract(payload)
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

        platform = detect_platform(payload.url)
        caption_result: SpeechToTextResult | None = None
        prefetched_speech_result: SpeechToTextResult | None = None
        prefetched_vision_result: FrameVisionResult | None = None
        if platform == "youtube":
            # Long-form YouTube is caption-only. Metadata extraction through
            # yt-dlp can make a healthy cached-caption import wait for several
            # minutes, so it must not be part of this path. Shorts continue
            # through the reel branch below and retain metadata/media handling.
            metadata = UrlMetadata(
                originalUrl=payload.url,
                canonicalUrl=canonicalize_url(payload.url),
                platform=platform,
            )
            metadata_duration = 0.0
            caption_result = self.youtube_transcript.fetch(
                payload.url,
                languages=payload.stt_language,
            )
            timings["youtubeMetadataSkipped"] = 1.0
            if caption_result.status == "ok" and caption_result.text:
                artifacts = MediaArtifacts()
                media_timings = {
                    "youtubeTranscriptAvailable": 1.0,
                    "mediaDownloadSkipped": 1.0,
                }
            else:
                artifacts = MediaArtifacts()
                media_timings = {
                    "youtubeTranscriptUnavailable": 1.0,
                    "mediaDownloadSkipped": 1.0,
                }
        else:
            with ThreadPoolExecutor(max_workers=2) as executor:
                metadata_future = executor.submit(load_metadata)
                media_future = executor.submit(
                    self._prepare_media_and_extract_signals,
                    payload,
                    work_dir,
                    metadata_future,
                )
                metadata, metadata_duration = metadata_future.result()
                (
                    artifacts,
                    media_timings,
                    prefetched_speech_result,
                    prefetched_vision_result,
                ) = media_future.result()

        timings["loadMetadata"] = metadata_duration
        timings["prepareSourceWall"] = time.perf_counter() - source_start
        timings.update(media_timings)

        effective_destination = (
            usable_destination(payload.destination)
            or infer_destination_from_text(metadata.title, metadata.description)
            or None
        )

        speech_result = caption_result or prefetched_speech_result or SpeechToTextResult(
            text="",
            status="skipped",
            durationSeconds=0.0,
        )
        vision_result = prefetched_vision_result or FrameVisionResult()
        expected_place_count = _expected_place_count(
            metadata.title,
            metadata.description,
            speech_result.text,
        )
        if (
            platform == "youtube"
            and speech_result.status == "ok"
            and speech_result.text
            and not speech_result.observations
            and self.caption_structurer is not None
            and not _metadata_has_authoritative_blueprint(metadata)
        ):
            structure_result = self.caption_structurer.structure(
                caption=speech_result.text,
                metadata=metadata,
                destination=effective_destination,
            )
            timings["captionStructuring"] = (
                structure_result.duration_seconds
            )
            timings["captionStructuringUsed"] = 1.0
            if structure_result.status == "ok" and structure_result.observations:
                speech_result = speech_result.model_copy(
                    update={"observations": structure_result.observations}
                )
                expected_place_count = (
                    structure_result.expected_place_count
                    or expected_place_count
                )
            elif structure_result.status == "failed":
                timings["captionStructuringFailed"] = 1.0
        elif platform == "youtube" and speech_result.text:
            timings["captionStructuringSkipped"] = 1.0
        start = time.perf_counter()
        stt_prompt = payload.stt_initial_prompt
        if stt_prompt is None and effective_destination:
            stt_prompt = (
                f"This is a travel itinerary video about {effective_destination}. "
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
                if platform != "youtube" and artifacts.audio_path is not None
                and prefetched_speech_result is None
                else None
            )
            vision_future = (
                executor.submit(
                    (self.frame_vision or GeminiReelFrameVision()).analyze,
                    artifacts.frame_paths,
                    destination=effective_destination,
                )
                if artifacts.frame_paths
                and prefetched_vision_result is None
                else None
            )
            if speech_future is not None:
                try:
                    speech_result = speech_future.result()
                except (RuntimeError, httpx.HTTPError) as exc:
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
        if prefetched_speech_result is None and prefetched_vision_result is None:
            timings["extractSignalsWall"] = time.perf_counter() - start

        context_arguments = {
            "metadata": metadata,
            "transcript": speech_result.text,
            "speech_observations": (
                speech_result.observations
                if speech_result.observations
                else None
            ),
            "destination": effective_destination,
        }
        if expected_place_count is not None:
            context_arguments["expected_place_count"] = expected_place_count
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
        if (
            timings.get("captionStructuringUsed") == 1.0
            and not speech_result.observations
            and expected_place_count is not None
        ):
            # A known-size list must not fall back to permissive raw-caption
            # heuristics after structured extraction fails. Failing closed here
            # saves resolver/Planner latency and avoids a plausible-looking but
            # incomplete itinerary.
            context = context.model_copy(
                update={
                    "extraction_coverage": min(
                        context.extraction_coverage or 0.0,
                        0.39,
                    ),
                    "coverage_status": "insufficient",
                }
            )
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
                platform != "youtube"
                and
                not speech_result.text
                and artifacts.audio_path is None
                and not artifacts.frame_paths
                and not context.extracted_places
            ),
            speechToText=speech_result,
            frameVision=vision_result,
            extractedContext=context,
            timings=timings,
        )
        return result

    def _prepare_media_and_extract_signals(
        self,
        payload: UrlReelInput,
        work_dir: Path,
        metadata_future: Future[tuple[UrlMetadata, float]] | None = None,
    ) -> tuple[
        MediaArtifacts,
        dict[str, float],
        SpeechToTextResult,
        FrameVisionResult,
    ]:
        """Run the media branch without waiting for platform metadata."""

        artifacts, timings = self.media.prepare(
            canonicalize_url(payload.url),
            work_dir=work_dir,
        )
        signal_started_at = time.perf_counter()
        prompt_destination = usable_destination(payload.destination)
        if not prompt_destination and metadata_future is not None:
            metadata, _duration = metadata_future.result()
            prompt_destination = (
                infer_destination_from_text(metadata.title, metadata.description)
                or None
            )
        stt_prompt = payload.stt_initial_prompt
        if stt_prompt is None and prompt_destination:
            stt_prompt = (
                f"This is a travel itinerary video about {prompt_destination}. "
                "It may mention destinations, cafes, restaurants, attractions, "
                "hotels, neighborhoods, and transport."
            )
        speech_result = SpeechToTextResult(
            text="",
            status="skipped",
            durationSeconds=0.0,
        )
        vision_result = FrameVisionResult()
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
                    destination=prompt_destination,
                )
                if artifacts.frame_paths
                else None
            )
            if speech_future is not None:
                try:
                    speech_result = speech_future.result()
                except (RuntimeError, httpx.HTTPError) as exc:
                    timings["speechToTextFailed"] = 1.0
                    speech_result = SpeechToTextResult(
                        text="",
                        status="failed",
                        error=str(exc),
                        durationSeconds=time.perf_counter() - signal_started_at,
                    )
            if vision_future is not None:
                try:
                    vision_result = vision_future.result()
                except (RuntimeError, httpx.HTTPError) as exc:
                    timings["frameVisionFailed"] = 1.0
                    vision_result = FrameVisionResult(
                        status="failed",
                        error=str(exc),
                        durationSeconds=time.perf_counter() - signal_started_at,
                    )
        timings["extractSignalsWall"] = time.perf_counter() - signal_started_at
        return artifacts, timings, speech_result, vision_result


def _metadata_has_authoritative_blueprint(metadata: UrlMetadata) -> bool:
    chapters = metadata.raw.get("chapters")
    if isinstance(chapters, list):
        meaningful_chapters = [
            chapter
            for chapter in chapters
            if isinstance(chapter, dict)
            and isinstance(chapter.get("title"), str)
            and chapter["title"].strip()
            and not re.search(
                r"\b(?:intro(?:duction)?|outro|conclusion|subscribe|"
                r"travel tips?|summary)\b",
                chapter["title"],
                flags=re.IGNORECASE,
            )
        ]
        if len(meaningful_chapters) >= 2:
            return True
    description = metadata.description or ""
    numbered = re.findall(
        r"(?:^|\s)(?:#?\d{1,2}[.)]|(?:number|no\.?|số)\s+"
        r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"một|hai|ba|bốn|tư|năm|sáu|bảy|tám|chín|mười))\s+",
        description,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return len(numbered) >= 2


def _expected_place_count(*texts: str | None) -> int | None:
    joined = "\n".join(text for text in texts if text)
    patterns = (
        r"\btop\s+(?P<count>\d{1,2})\b",
        r"\b(?P<count>\d{1,2})\s+(?:địa điểm|places?|spots?|stops?|things to do)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, joined, flags=re.IGNORECASE)
        if match:
            count = int(match.group("count"))
            if 1 <= count <= 100:
                return count
    return None
