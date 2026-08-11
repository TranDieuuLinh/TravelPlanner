import asyncio

from app.modules.explorer.adapters.tiktok_html import (
    FallbackUrlMediaClient,
    TikTokHtmlMediaClient,
)
from app.modules.explorer.ports import DownloadedMedia


class FailingMediaDownloader:
    async def download(self, url: str, target_dir: str):
        raise RuntimeError("blocked")


class SuccessfulMediaDownloader:
    async def download(self, url: str, target_dir: str):
        return DownloadedMedia(f"{target_dir}/fallback.mp4", {"title": "fallback"})


def test_tiktok_media_uses_fallback_after_primary_failure(tmp_path) -> None:
    client = FallbackUrlMediaClient(
        FailingMediaDownloader(), SuccessfulMediaDownloader()
    )

    result = asyncio.run(client.download("https://www.tiktok.com/@a/video/1", str(tmp_path)))

    assert result.file_path.endswith("fallback.mp4")
    assert result.metadata["title"] == "fallback"


def test_tiktok_html_extracts_matching_embedded_video() -> None:
    page = """
    <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">
    {"scope":{"itemStruct":{"id":"123","desc":"Hanoi guide",
    "author":{"nickname":"Two Peas"},"challenges":[{"title":"hanoi"}],
    "video":{"duration":12,"playAddr":"https://v16-webapp-prime.tiktok.com/video.mp4"}}}}
    </script>
    """

    item = TikTokHtmlMediaClient._extract_item(
        page, "https://www.tiktok.com/@two_peas/video/123"
    )

    assert TikTokHtmlMediaClient._media_url(item).endswith("video.mp4")
    assert TikTokHtmlMediaClient._metadata(item) == {
        "id": "123",
        "title": "TikTok by Two Peas",
        "description": "Hanoi guide",
        "uploader": "Two Peas",
        "duration": 12,
        "location": None,
        "tags": ["hanoi"],
    }
