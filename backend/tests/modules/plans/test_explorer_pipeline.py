from __future__ import annotations

import asyncio
from typing import Any

from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.schema import (
    ExploreBundleDraft,
    ExploreImageContext,
    FullExploreRequest,
)
from app.modules.plans.explorer.tools.image_ocr import ImageUploadPayload
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
    assert not hasattr(result, "places")
    assert not hasattr(result, "persistence_status")
    assert url_reels.inputs == []
    assert formatter.payload is payload
    assert formatter.url_reel_results == []


def test_url_is_extracted_before_formatter_runs() -> None:
    formatter = RecordingFormatter()
    url_reels = RecordingUrlReels()
    image_ocr = RecordingImageOcr()
    service = build_service(formatter, url_reels, image_ocr)
    payload = FullExploreRequest(
        rawRequest="Xem URL này và tạo chuyến đi Hội An",
        destination="Hội An",
        urls=["https://example.com/reel"],
    )

    asyncio.run(service.explore_full(payload))

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

    asyncio.run(
        service.explore_from_intake(
            raw_request="Đọc ảnh này và tạo chuyến đi Hội An",
            destination="Hội An",
            urls=[],
            images=[image],
        )
    )

    assert len(image_ocr.calls) == 1
    assert formatter.payload is not None
    assert formatter.payload.image_contexts[0].ocr_text == (
        "Bánh mì Phượng, Hội An"
    )
    assert formatter.url_reel_results == []
    assert image.data == b""
