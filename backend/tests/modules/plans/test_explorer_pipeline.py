from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.schema import (
    ExploreBundleDraft,
    ExploreImageContext,
    FullExploreRequest,
)
from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    ExtractedPlace,
    MediaArtifacts,
    SpeechToTextResult,
    UrlMetadata,
    UrlReelExtractionResult,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.explorer.response_formatter import (
    _complete_constraint_policy,
)
from app.modules.plans.explorer.timing import ExplorerTimingLogger
from app.modules.plans.repository import PlanRepository
from app.modules.plans.service import PlanService


class RecordingFormatter:
    def __init__(self) -> None:
        self.payload: FullExploreRequest | None = None
        self.url_reel_results: list[Any] | None = None
        self.response = ExploreBundleDraft.model_validate(
            {
                "explorer": {
                    "intent": {"destination": "Hội An"},
                    "tripSpec": {"days": 3},
                    "assumptions": [],
                    "missingInfoQuestions": [],
                },
                "places": {"placeCandidates": []},
            }
        )
        self.context_called = False

    async def format(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[Any] | None = None,
    ) -> Any:
        self.payload = payload
        self.url_reel_results = url_reel_results
        return self.response

    async def format_context(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[Any],
    ) -> Any:
        self.payload = payload
        self.url_reel_results = url_reel_results
        self.context_called = True
        return self.response.explorer


class RecordingUrlReels:
    def __init__(
        self,
        *,
        count: int = 1,
        source_days: list[int | None] | None = None,
    ) -> None:
        self.inputs: list[Any] = []
        self.count = count
        self.source_days = source_days

    def extract(self, payload: Any) -> UrlReelExtractionResult:
        self.inputs.append(payload)
        return _url_result(
            payload.url,
            count=self.count,
            source_days=self.source_days,
        )


class RecordingImageOcr:
    def __init__(self) -> None:
        self.calls: list[tuple[list[ImageUploadPayload], str | None]] = []

    async def extract_many(
        self,
        images: list[ImageUploadPayload],
        *,
        destination: str | None,
    ) -> list[ExploreImageContext]:
        self.calls.append((images, destination))
        return [
            ExploreImageContext(
                fileName=image.file_name,
                mimeType=image.mime_type or "application/octet-stream",
                ocrText="Bánh mì Phượng, Hội An",
            )
            for image in images
        ]


class RecordingResolver:
    async def resolve_many(
        self,
        candidates: list[Any],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        return [
            PlaceResolution(
                candidate=candidate,
                status="resolved",
                provider="fake_places",
                name=candidate.name,
                city=destination,
                latitude="21.0285",
                longitude="105.8542",
                dataConfidence="high",
            )
            for candidate in candidates
        ]


def build_service(
    formatter: RecordingFormatter,
    url_reels: RecordingUrlReels,
    image_ocr: RecordingImageOcr,
) -> PlanService:
    return PlanService(
        repository=PlanRepository(),
        explore_formatter=formatter,  # type: ignore[arg-type]
        main_workflow=object(),  # type: ignore[arg-type]
        backup_workflow=object(),  # type: ignore[arg-type]
        image_ocr=image_ocr,  # type: ignore[arg-type]
        url_reels=url_reels,  # type: ignore[arg-type]
        place_resolver=RecordingResolver(),  # type: ignore[arg-type]
    )


def _url_result(
    url: str,
    *,
    count: int,
    source_days: list[int | None] | None = None,
    needs_image_upload: bool = False,
) -> UrlReelExtractionResult:
    days = source_days or [None] * count
    details = [
        ExtractedPlace(
            name=f"URL stop {index}",
            sourceOrder=index,
            sourceDay=days[index - 1],
        )
        for index in range(1, count + 1)
    ]
    return UrlReelExtractionResult(
        url=url,
        platform="tiktok",
        metadata=UrlMetadata(
            originalUrl=url,
            canonicalUrl=url,
            platform="tiktok",
        ),
        artifacts=MediaArtifacts(),
        needsImageUpload=needs_image_upload,
        speechToText=SpeechToTextResult(
            text="",
            status="skipped",
            durationSeconds=0,
        ),
        extractedContext=ExtractedContext(
            extractedPlaces=[detail.name for detail in details],
            extractedPlaceDetails=details,
            confidence=0.9 if details else 0.3,
        ),
        timings={
            "totalExtraction": 1.2,
            "loadMetadata": 0.1,
            "extractSignalsWall": 0.8,
            "speechToText": 0.7,
            "frameVision": 0.6,
            "sampledFrames": 4.0,
        },
    )


def test_plain_prompt_goes_directly_to_formatter() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels()
    image_ocr = RecordingImageOcr()
    service = build_service(formatter, url_reels, image_ocr)
    payload = FullExploreRequest(
        rawRequest="Hội An 3 ngày, ưu tiên ẩm thực",
        destination="Hội An",
        userState={"userId": "user-1"},
    )

    result = asyncio.run(service.explore_full(payload))

    assert result.explorer.intent.destination == "Hội An"
    assert result.intake_id
    assert result.user_id == "user-1"
    assert result.allow_finder_suggestions is True
    assert not hasattr(result, "places")
    assert not hasattr(result, "persistence_status")
    assert url_reels.inputs == []
    assert formatter.payload is payload
    assert formatter.url_reel_results == []


def test_url_is_extracted_before_formatter_runs() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels(count=1)
    image_ocr = RecordingImageOcr()
    service = build_service(formatter, url_reels, image_ocr)
    payload = FullExploreRequest(
        rawRequest="Xem URL này và tạo chuyến đi Hội An",
        destination="Hội An",
        urls=["https://example.com/reel"],
    )

    result = asyncio.run(service.explore_full(payload))

    assert result.explorer.trip_spec.days == 3
    assert result.allow_finder_suggestions is True
    assert [item.url for item in url_reels.inputs] == [
        "https://example.com/reel"
    ]
    assert formatter.context_called is True
    assert formatter.url_reel_results is not None
    assert formatter.url_reel_results[0].url == "https://example.com/reel"


def test_explorer_timing_is_returned_and_appended_without_raw_content(
    tmp_path,
) -> None:
    formatter = RecordingFormatter()
    service = build_service(
        formatter,
        RecordingUrlReels(count=2),
        RecordingImageOcr(),
    )
    log_path = tmp_path / "explorer-timings.jsonl"
    service.explorer_timing_logger = ExplorerTimingLogger(log_path)

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Private prompt content",
                destination="Hà Nội",
                urls=["https://example.com/private-query"],
            )
        )
    )

    assert result.timing_report is not None
    assert result.timing_report.intake_id == result.intake_id
    assert result.timing_report.status == "completed"
    assert result.timing_report.candidate_count == 2
    assert result.timing_report.resolved_count == 2
    assert result.timing_report.provider_counts == {"fake_places": 2}
    assert result.timing_report.resolved_provider_counts == {
        "fake_places": 2
    }
    assert {
        stage.key for stage in result.timing_report.stages
    } >= {
        "urlExtractionWall",
        "candidateAggregation",
        "formatter",
        "placeResolution",
        "postProcessing",
        "persistence",
    }
    persisted = json.loads(log_path.read_text(encoding="utf-8"))
    assert persisted["intakeId"] == result.intake_id
    assert persisted["sources"][0]["sampledFrames"] == 4
    assert persisted["sources"][0]["extractedPlaceCount"] == 2
    assert persisted["sources"][0]["candidateCount"] == 2
    assert persisted["sources"][0]["resolvedCount"] == 2
    assert persisted["sources"][0]["providerCounts"] == {
        "fake_places": 2
    }
    assert persisted["sources"][0]["resolvedProviderCounts"] == {
        "fake_places": 2
    }
    serialized = json.dumps(persisted)
    assert "Private prompt content" not in serialized
    assert "private-query" not in serialized


def test_image_ocr_is_added_before_formatter_runs() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels()
    image_ocr = RecordingImageOcr()
    service = build_service(formatter, url_reels, image_ocr)
    image = ImageUploadPayload(
        file_name="note.png",
        mime_type="image/png",
        data=b"image",
    )

    result = asyncio.run(
        service.explore_from_intake(
            raw_request="Đọc ảnh này và tạo chuyến đi Hội An",
            destination="Hội An",
            urls=[],
            images=[image],
        )
    )

    assert len(image_ocr.calls) == 1
    assert result.explorer.trip_spec.days == 3
    assert result.allow_finder_suggestions is True
    assert formatter.payload is not None
    assert formatter.payload.image_contexts[0].ocr_text == (
        "Bánh mì Phượng, Hội An"
    )
    assert formatter.url_reel_results == []
    assert image.data == b""


def test_url_without_requested_duration_allows_sparse_last_day_fill() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels(count=10)
    service = build_service(formatter, url_reels, RecordingImageOcr())

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Tạo lịch trình từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
            )
        )
    )

    assert result.explorer.trip_spec.days == 4
    assert result.allow_finder_suggestions is True
    assert any(
        "inferred as 4 days" in assumption
        for assumption in result.explorer.assumptions
    )


def test_url_with_two_day_coverage_keeps_default_and_allows_empty_day_fill() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels(
        count=5,
        source_days=[1, 1, 1, 2, 2],
    )
    service = build_service(formatter, url_reels, RecordingImageOcr())

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Tạo lịch trình từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
            )
        )
    )

    assert result.explorer.trip_spec.days == 3
    assert result.allow_finder_suggestions is True
    assert any(
        "default 3-day duration was kept" in assumption
        for assumption in result.explorer.assumptions
    )


def test_url_with_more_requested_days_allows_finder_for_empty_days() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels(count=5)
    service = build_service(formatter, url_reels, RecordingImageOcr())

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Hà Nội 10 ngày từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
                tripSpec={"days": 10},
            )
        )
    )

    assert result.explorer.trip_spec.days == 10
    assert result.allow_finder_suggestions is True


def test_seven_day_url_allows_finder_when_late_days_are_sparse() -> None:
    formatter = RecordingFormatter()
    source_days = [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 6, 7]
    service = build_service(
        formatter,
        RecordingUrlReels(count=12, source_days=source_days),
        RecordingImageOcr(),
    )

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Tạo lịch trình Hà Nội 7 ngày từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
                tripSpec={"days": 7},
            )
        )
    )

    assert result.explorer.trip_spec.days == 7
    assert result.allow_finder_suggestions is True


def test_unresolved_url_places_keep_default_duration_and_enable_finder() -> None:
    formatter = RecordingFormatter()
    service = build_service(
        formatter,
        RecordingUrlReels(count=10),
        RecordingImageOcr(),
    )

    class UnresolvedResolver:
        async def resolve_many(
            self,
            candidates: list[Any],
            *,
            destination: str,
        ) -> list[PlaceResolution]:
            return [
                PlaceResolution(
                    candidate=candidate,
                    status="unresolved",
                    name=candidate.name,
                    city=destination,
                    dataConfidence="low",
                )
                for candidate in candidates
            ]

    service.place_resolver = UnresolvedResolver()  # type: ignore[assignment]

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Tạo lịch trình từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
            )
        )
    )

    assert result.explorer.trip_spec.days == 3
    assert result.allow_finder_suggestions is True


def test_explicit_shorter_duration_wins_over_large_url_itinerary() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels(count=20)
    service = build_service(formatter, url_reels, RecordingImageOcr())

    result = asyncio.run(
        service.explore_full(
            FullExploreRequest(
                rawRequest="Hà Nội 6 ngày từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
                tripSpec={"days": 6},
            )
        )
    )

    assert result.explorer.trip_spec.days == 6
    assert result.allow_finder_suggestions is False


def test_url_formatter_and_resolver_run_concurrently() -> None:
    async def scenario() -> None:
        formatter_started = asyncio.Event()
        resolver_started = asyncio.Event()

        class CoordinatedFormatter(RecordingFormatter):
            async def format_context(
                self,
                payload: FullExploreRequest,
                *,
                url_reel_results: list[Any],
            ) -> Any:
                formatter_started.set()
                await asyncio.wait_for(resolver_started.wait(), timeout=0.5)
                return await super().format_context(
                    payload,
                    url_reel_results=url_reel_results,
                )

        class CoordinatedResolver(RecordingResolver):
            async def resolve_many(
                self,
                candidates: list[Any],
                *,
                destination: str,
            ) -> list[PlaceResolution]:
                resolver_started.set()
                await asyncio.wait_for(formatter_started.wait(), timeout=0.5)
                return await super().resolve_many(
                    candidates,
                    destination=destination,
                )

        formatter = CoordinatedFormatter()
        service = build_service(
            formatter,
            RecordingUrlReels(count=2),
            RecordingImageOcr(),
        )
        service.place_resolver = CoordinatedResolver()  # type: ignore[assignment]

        result = await service.explore_full(
            FullExploreRequest(
                rawRequest="Tạo lịch trình từ URL",
                destination="Hà Nội",
                urls=["https://example.com/reel"],
            )
        )

        assert result.explorer.intent.destination == "Hội An"
        assert formatter.context_called is True

    asyncio.run(scenario())


def test_unavailable_url_media_does_not_generate_empty_ready_plan() -> None:
    formatter = RecordingFormatter()

    class UnavailableUrlReels(RecordingUrlReels):
        def extract(self, payload: Any) -> Any:
            self.inputs.append(payload)
            return _url_result(
                payload.url,
                count=0,
                needs_image_upload=True,
            )

    service = build_service(
        formatter,
        UnavailableUrlReels(),
        RecordingImageOcr(),
    )

    with pytest.raises(RuntimeError, match="upload screenshots"):
        asyncio.run(
            service.explore_full(
                FullExploreRequest(
                    rawRequest="Tạo lịch trình từ URL",
                    destination="Hà Nội",
                    urls=["https://example.com/reel"],
                )
            )
        )


def test_failed_url_ocr_does_not_generate_empty_ready_plan() -> None:
    formatter = RecordingFormatter()

    class FailedOcrUrlReels(RecordingUrlReels):
        def extract(self, payload: Any) -> Any:
            self.inputs.append(payload)
            return _url_result(
                payload.url,
                count=0,
                needs_image_upload=False,
            )

    service = build_service(
        formatter,
        FailedOcrUrlReels(),
        RecordingImageOcr(),
    )

    with pytest.raises(RuntimeError, match="OCR/STT may have failed"):
        asyncio.run(
            service.explore_full(
                FullExploreRequest(
                    rawRequest="Tạo lịch trình từ URL",
                    destination="Hà Nội",
                    urls=["https://example.com/reel"],
                )
            )
        )
def test_constraint_policy_is_completed_from_vietnamese_request() -> None:
    formatter = RecordingFormatter()

    completed = _complete_constraint_policy(
        formatter.response,
        (
            "Giúp tôi lên kế hoạch đi Hải Phòng trong 5 ngày. "
            "Tôi không thích đi nghĩa trang, chỉ đi ven biển."
        ),
    )

    policy = completed.explorer.intent.constraint_policy
    assert policy.excluded_place_types == ["cemetery"]
    assert policy.geographic_scope.type.value == "coastal"
