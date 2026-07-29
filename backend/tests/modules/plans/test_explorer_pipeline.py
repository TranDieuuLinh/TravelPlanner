from __future__ import annotations

import asyncio
from typing import Any
from types import SimpleNamespace

import pytest

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.schema import (
    ExploreBundleDraft,
    ExploreImageContext,
    FullExploreRequest,
    UnifiedPlaceCandidate,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
from app.modules.plans.explorer.response_formatter import (
    _complete_constraint_policy,
)
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

    async def format(
        self,
        payload: FullExploreRequest,
        *,
        url_reel_results: list[Any] | None = None,
    ) -> Any:
        self.payload = payload
        self.url_reel_results = url_reel_results
        return self.response


class RecordingUrlReels:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    def extract(self, payload: Any) -> dict[str, str]:
        self.inputs.append(payload)
        return {"url": payload.url}


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


class PassthroughAggregator:
    def aggregate(self, **kwargs: Any) -> list[Any]:
        return list(kwargs["generated"])


class RecordingResolver:
    async def resolve_many(
        self,
        candidates: list[Any],
        *,
        destination: str,
    ) -> list[PlaceResolution]:
        return []


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
        place_candidate_aggregator=PassthroughAggregator(),  # type: ignore[arg-type]
        place_resolver=RecordingResolver(),  # type: ignore[arg-type]
    )


def _url_candidates(count: int) -> list[UnifiedPlaceCandidate]:
    return [
        UnifiedPlaceCandidate.model_validate(
            {
                "name": f"URL stop {index}",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "sourceOrder": index,
            }
        )
        for index in range(1, count + 1)
    ]


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

    assert result.explorer is formatter.response.explorer
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
    formatter.response.places.place_candidates = _url_candidates(1)
    url_reels = RecordingUrlReels()
    image_ocr = RecordingImageOcr()
    service = build_service(formatter, url_reels, image_ocr)
    payload = FullExploreRequest(
        rawRequest="Xem URL này và tạo chuyến đi Hội An",
        destination="Hội An",
        urls=["https://example.com/reel"],
    )

    result = asyncio.run(service.explore_full(payload))

    assert result.allow_finder_suggestions is False
    assert [item.url for item in url_reels.inputs] == [
        "https://example.com/reel"
    ]
    assert formatter.url_reel_results == [
        {"url": "https://example.com/reel"}
    ]


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
    assert result.allow_finder_suggestions is False
    assert formatter.payload is not None
    assert formatter.payload.image_contexts[0].ocr_text == (
        "Bánh mì Phượng, Hội An"
    )
    assert formatter.url_reel_results == []
    assert image.data == b""


def test_url_without_requested_duration_infers_enough_days_for_all_stops() -> None:
    formatter = RecordingFormatter()
    formatter.response.places.place_candidates = _url_candidates(10)
    url_reels = RecordingUrlReels()
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
    assert result.allow_finder_suggestions is False
    assert any(
        "inferred as 4 days" in assumption
        for assumption in result.explorer.assumptions
    )


def test_url_with_more_requested_days_allows_finder_for_empty_days() -> None:
    formatter = RecordingFormatter()
    formatter.response.places.place_candidates = _url_candidates(5)
    url_reels = RecordingUrlReels()
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


def test_explicit_shorter_duration_wins_over_large_url_itinerary() -> None:
    formatter = RecordingFormatter()
    formatter.response.places.place_candidates = _url_candidates(20)
    url_reels = RecordingUrlReels()
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


def test_unavailable_url_media_does_not_generate_empty_ready_plan() -> None:
    formatter = RecordingFormatter()

    class UnavailableUrlReels(RecordingUrlReels):
        def extract(self, payload: Any) -> Any:
            self.inputs.append(payload)
            return SimpleNamespace(
                url=payload.url,
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
            return SimpleNamespace(
                url=payload.url,
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
