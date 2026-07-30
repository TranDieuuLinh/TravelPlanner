from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from app.modules.plans.explorer.schema import (
    ExplorerSourceTiming,
    ExplorerTimingReport,
    ExplorerTimingStage,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    UrlReelExtractionResult,
)

logger = logging.getLogger(__name__)

_DURATION_LABELS = {
    "totalExtraction": "Tổng URL extractor",
    "loadMetadata": "Đọc metadata",
    "prepareSourceWall": "Chuẩn bị nguồn (wall)",
    "downloadVideo": "Tải video",
    "prepareSignalsWall": "Tách audio và frame",
    "speechToText": "Speech-to-text",
    "frameVision": "Frame vision / OCR",
    "extractSignalsWall": "STT + vision song song (wall)",
    "contextExtraction": "Chuẩn hóa candidate",
}
_STAGE_ORDER = {
    "imageExtractionWall": 0,
    "urlExtractionWall": 1,
    "candidateAggregation": 2,
    "formatter": 3,
    "placeResolution": 4,
    "postProcessing": 5,
    "persistence": 6,
}


class ExplorerTimingTrace:
    def __init__(
        self,
        intake_id: str,
        *,
        url_count: int,
        image_count: int,
    ) -> None:
        self.intake_id = intake_id
        self.url_count = url_count
        self.image_count = image_count
        self.started_at = time.perf_counter()
        self.stages: list[ExplorerTimingStage] = []
        self.sources: list[ExplorerSourceTiming] = []
        self.candidate_count = 0
        self.resolved_count = 0
        self.persisted_count = 0
        self.provider_counts: dict[str, int] = {}

    def record_stage(
        self,
        key: str,
        label: str,
        started_at: float,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.stages.append(
            ExplorerTimingStage(
                key=key,
                label=label,
                durationSeconds=_seconds(time.perf_counter() - started_at),
                details=details or {},
            )
        )

    def add_url_results(
        self,
        results: list[UrlReelExtractionResult],
    ) -> None:
        self.sources = [
            ExplorerSourceTiming(
                sourceIndex=index,
                platform=result.platform,
                totalSeconds=_seconds(
                    result.timings.get("totalExtraction", 0.0)
                ),
                stages=[
                    ExplorerTimingStage(
                        key=key,
                        label=_DURATION_LABELS[key],
                        durationSeconds=_seconds(value),
                    )
                    for key, value in result.timings.items()
                    if key in _DURATION_LABELS
                    and key != "totalExtraction"
                ],
                sampledFrames=int(
                    result.timings.get("sampledFrames", 0.0)
                ),
                speechStatus=result.speech_to_text.status,
                visionStatus=result.frame_vision.status,
                extractedPlaceCount=len(
                    result.extracted_context.extracted_place_details
                ),
            )
            for index, result in enumerate(results, start=1)
        ]

    def finish(
        self,
        *,
        status: str,
        log_file: str | None,
    ) -> ExplorerTimingReport:
        return ExplorerTimingReport(
            intakeId=self.intake_id,
            status=status,
            totalSeconds=_seconds(time.perf_counter() - self.started_at),
            stages=sorted(
                self.stages,
                key=lambda stage: _STAGE_ORDER.get(stage.key, 100),
            ),
            sources=self.sources,
            urlCount=self.url_count,
            imageCount=self.image_count,
            candidateCount=self.candidate_count,
            resolvedCount=self.resolved_count,
            persistedCount=self.persisted_count,
            providerCounts=self.provider_counts,
            logFile=log_file,
        )


class ExplorerTimingLogger:
    _write_lock = threading.Lock()

    def __init__(
        self,
        path: Path,
        *,
        display_path: str = "backend/var/explorer-timings.jsonl",
    ) -> None:
        self.path = path
        self.display_path = display_path

    def write(self, report: ExplorerTimingReport) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(
                report.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            with self._write_lock:
                with self.path.open("a", encoding="utf-8") as output:
                    output.write(f"{line}\n")
        except OSError:
            logger.warning(
                "Could not append Explorer timing report for intake %s.",
                report.intake_id,
                exc_info=True,
            )


def _seconds(value: float) -> float:
    return round(max(0.0, value), 3)
