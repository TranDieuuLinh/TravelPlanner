import asyncio
from tempfile import TemporaryDirectory

from app.modules.explorer.adapters.url_sources import (
    _deduplicate_artifacts,
    metadata_artifacts,
)
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.models import (
    MediaAnalysisResult,
    SourceArtifact,
    SourceBranchFailure,
    SourceExtractionResult,
)
from app.modules.explorer.ports import (
    MediaAnalyzer,
    PrimaryEvidenceEvaluator,
    UrlMediaClient,
)
from app.shared.contracts.agent import AgentError


class YouTubeTranscriptSourceExtractor:
    def __init__(
        self,
        captions,
        audio,
        transcriber,
        *,
        coverage_evaluator: PrimaryEvidenceEvaluator | None = None,
        media_client: UrlMediaClient | None = None,
        analyzer: MediaAnalyzer | None = None,
        max_concurrency: int = 1,
    ) -> None:
        self.captions = captions
        self.audio = audio
        self.transcriber = transcriber
        self.coverage_evaluator = coverage_evaluator
        self.media_client = media_client
        self.analyzer = analyzer
        self._limiter = asyncio.Semaphore(max(1, max_concurrency))

    async def extract(self, url: str, *, source_index: int, raw_prompt: str | None):
        async with self._limiter:
            return await self._extract(
                url,
                source_index=source_index,
                raw_prompt=raw_prompt,
            )

    async def _extract(
        self,
        url: str,
        *,
        source_index: int,
        raw_prompt: str | None,
    ) -> SourceExtractionResult:
        with TemporaryDirectory(prefix="explorer-youtube-") as work_dir:
            try:
                bundle = await self.captions.fetch(url, work_dir)
            except ExplorerOperationError:
                bundle = None

            metadata = bundle.metadata if bundle is not None else {}
            duration = bundle.duration_seconds if bundle is not None else None
            primary = _deduplicate_artifacts([
                *metadata_artifacts(metadata, url),
                *(bundle.artifacts if bundle is not None else []),
            ])
            has_native_transcript = any(
                artifact.artifact_type == "transcript" for artifact in primary
            )
            primary_sufficient = await self._is_sufficient(
                primary,
                transcript_timeline_ratio=1.0 if has_native_transcript else None,
                raw_prompt=raw_prompt,
            )

            if primary_sufficient:
                return self._result(
                    url,
                    source_index,
                    primary,
                    duration=duration,
                    transcript_complete=has_native_transcript,
                )

            if has_native_transcript:
                analysis = await self._ocr_fallback(url, work_dir)
                artifacts = _deduplicate_artifacts([
                    *primary,
                    *analysis.artifacts,
                ])
                return self._result(
                    url,
                    source_index,
                    artifacts,
                    duration=duration,
                    transcript_complete=True,
                    analysis=analysis,
                )

            audio_path, audio_metadata = await self.audio.download(url, work_dir)
            transcript, duration = await self.transcriber.transcribe(
                audio_path,
                work_dir,
                url,
            )
            artifacts = _deduplicate_artifacts([
                *primary,
                *metadata_artifacts(audio_metadata, url),
                *transcript,
            ])
            transcript_sufficient = await self._is_sufficient(
                artifacts,
                transcript_timeline_ratio=1.0,
                raw_prompt=raw_prompt,
            )
            analysis = MediaAnalysisResult()
            if not transcript_sufficient:
                analysis = await self._ocr_fallback(url, work_dir)
                artifacts = _deduplicate_artifacts([
                    *artifacts,
                    *analysis.artifacts,
                ])
            return self._result(
                url,
                source_index,
                artifacts,
                duration=duration,
                transcript_complete=True,
                analysis=analysis,
            )

    async def _is_sufficient(
        self,
        artifacts: list[SourceArtifact],
        *,
        transcript_timeline_ratio: float | None,
        raw_prompt: str | None,
    ) -> bool:
        if self.coverage_evaluator is None:
            return any(
                artifact.artifact_type == "transcript" for artifact in artifacts
            )
        try:
            coverage = await self.coverage_evaluator.evaluate(
                artifacts,
                transcript_timeline_ratio=transcript_timeline_ratio,
                raw_prompt=raw_prompt,
            )
        except Exception:
            return False
        return coverage.sufficient

    async def _ocr_fallback(
        self,
        url: str,
        work_dir: str,
    ) -> MediaAnalysisResult:
        if self.media_client is None or self.analyzer is None:
            return MediaAnalysisResult()
        try:
            downloaded = await self.media_client.download(url, work_dir)
            return await self.analyzer.analyze(
                downloaded.file_path,
                work_dir,
                url,
                branches={"frame_ocr"},
            )
        except Exception as exc:
            if isinstance(exc, ExplorerOperationError):
                error = exc
            else:
                error = ExplorerOperationError(
                    "YOUTUBE_OCR_FALLBACK_FAILED",
                    "Không chạy được OCR fallback cho YouTube.",
                    retryable=True,
                )
            return MediaAnalysisResult(
                failures=[SourceBranchFailure(
                    branch="frame_ocr",
                    error=AgentError(
                        code=error.code,
                        message=str(error),
                        retryable=error.retryable,
                    ),
                )]
            )

    @staticmethod
    def _result(
        url: str,
        source_index: int,
        artifacts: list[SourceArtifact],
        *,
        duration: float | None,
        transcript_complete: bool,
        analysis: MediaAnalysisResult | None = None,
    ) -> SourceExtractionResult:
        failures = analysis.failures if analysis is not None else []
        return SourceExtractionResult(
            sourceIndex=source_index,
            sourceKind="url",
            sourceRef=url,
            status="partial" if failures else "succeeded",
            artifacts=artifacts,
            branchFailures=failures,
            sourceDurationSeconds=duration,
            analyzedDurationSeconds=duration if transcript_complete else None,
            coverageRatio=(
                1.0 if transcript_complete and duration is not None else None
            ),
            coverageStatus=(
                "complete"
                if transcript_complete and duration is not None
                else "unknown"
            ),
        )
