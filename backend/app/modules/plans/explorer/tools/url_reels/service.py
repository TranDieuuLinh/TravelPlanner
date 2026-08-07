from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

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
    RegionSourceStory,
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
            prefix="travelplanner_url_reel_",
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
        elif platform == "tiktok":
            # TikTok may challenge a client that opens the metadata request and
            # the media download at the same time.  Each branch already has up
            # to three yt-dlp/browser attempts, so overlapping them can create
            # a burst of requests and make an otherwise public video look
            # unavailable.  Resolve metadata first and hand the completed
            # result to the media/signal branch so the two TikTok fetches never
            # overlap.
            metadata, metadata_duration = load_metadata()
            metadata_future: Future[tuple[UrlMetadata, float]] = Future()
            metadata_future.set_result((metadata, metadata_duration))
            (
                artifacts,
                media_timings,
                prefetched_speech_result,
                prefetched_vision_result,
            ) = self._prepare_media_and_extract_signals(
                payload,
                work_dir,
                metadata_future,
            )
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
            if structure_result.status == "ok":
                speech_result = speech_result.model_copy(
                    update={
                        "observations": (
                            structure_result.observations
                            or speech_result.observations
                        ),
                        "region_story": structure_result.region_story,
                        "region_story_evidence": (
                            structure_result.region_story_evidence
                        ),
                    }
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

        metadata_story_result = None
        if (
            platform in {"tiktok", "instagram"}
            and self.caption_structurer is not None
            and (metadata.description or "").strip()
        ):
            metadata_story_result = self.caption_structurer.structure(
                caption=metadata.description or "",
                metadata=metadata,
                destination=effective_destination,
            )
            timings["regionStoryStructuring"] = (
                metadata_story_result.duration_seconds
            )

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
            if expected_place_count is None:
                observed_orders = {
                    observation.order
                    for observation in vision_result.observations
                    if observation.order is not None
                }
                if 1 in observed_orders and len(observed_orders) >= 2:
                    expected_place_count = max(observed_orders)
                    context_arguments["expected_place_count"] = (
                        expected_place_count
                    )
        context_start = time.perf_counter()
        context = self.context_extractor.extract(**context_arguments)
        region_story = None
        if metadata_story_result is not None and metadata_story_result.status == "ok":
            region_story = _grounded_region_story(
                story=metadata_story_result.region_story,
                evidence=metadata_story_result.region_story_evidence,
                source_text=metadata.description or "",
                evidence_type="caption",
                destination=effective_destination,
            )
        if region_story is None:
            region_story = _grounded_region_story(
                story=speech_result.region_story,
                evidence=speech_result.region_story_evidence,
                source_text=speech_result.text,
                evidence_type="stt",
                destination=effective_destination,
            )
        if region_story is not None:
            context = context.model_copy(update={"region_story": region_story})
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


def _grounded_region_story(
    *,
    story: str,
    evidence: str,
    source_text: str,
    evidence_type: Literal["caption", "stt"],
    destination: str | None,
) -> RegionSourceStory | None:
    """Accept a region story only when its exact evidence exists in the source."""

    story = " ".join(story.split()).strip()
    evidence = " ".join(evidence.split()).strip()
    normalized_source = " ".join(source_text.casefold().split())
    normalized_evidence = " ".join(evidence.casefold().split())
    if not story or len(evidence) < 8 or normalized_evidence not in normalized_source:
        return None
    story_key = re.sub(r"[^\w]+", " ", story.casefold()).strip()
    destination_key = re.sub(
        r"[^\w]+",
        " ",
        (destination or "").casefold(),
    ).strip()
    if not story_key or story_key == destination_key:
        return None
    if not re.search(
        r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]",
        story.casefold(),
    ):
        return None
    return RegionSourceStory(
        text=story,
        evidence=evidence,
        evidenceType=evidence_type,
        confidence=0.85,
    )
