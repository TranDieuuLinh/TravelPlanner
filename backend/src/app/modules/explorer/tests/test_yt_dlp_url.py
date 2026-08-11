import asyncio

import pytest

from app.modules.explorer.adapters import (
    RuleBasedExplorerDraftGenerator,
    YtDlpTikTokUrlSourceExtractor,
)
from app.modules.explorer.errors import ExplorerOperationError


class FakeMetadataClient:
    async def extract(self, url: str) -> dict:
        return {
            "title": "Ăn ngon Hà Nội",
            "description": (
                "Du lịch ở Hà Nội, ăn phở ở Phở Gia Truyền Bát Đàn"
            ),
            "tags": ["hanoi", "food"],
        }


def test_tiktok_metadata_becomes_url_evidence() -> None:
    extractor = YtDlpTikTokUrlSourceExtractor(
        FakeMetadataClient(), RuleBasedExplorerDraftGenerator()
    )
    result = asyncio.run(extractor.extract(
        "https://www.tiktok.com/@creator/video/123",
        source_index=0,
        raw_prompt=None,
    ))

    assert result.status == "succeeded"
    assert result.adm_candidates[0].value == "Hanoi"
    assert result.places[0].name == "Phở Gia Truyền Bát Đàn"
    assert result.places[0].source_places[0].origin == "url"
    assert result.notes[0].source_url == "https://www.tiktok.com/@creator/video/123"


def test_non_tiktok_url_is_rejected_before_client_call() -> None:
    extractor = YtDlpTikTokUrlSourceExtractor(
        FakeMetadataClient(), RuleBasedExplorerDraftGenerator()
    )

    with pytest.raises(ExplorerOperationError) as caught:
        asyncio.run(extractor.extract(
            "https://example.com/video",
            source_index=0,
            raw_prompt=None,
        ))

    assert caught.value.code == "UNSUPPORTED_URL"
    assert caught.value.retryable is False
