import asyncio
import re

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


class FakeMediaResponse:
    def __init__(self, status_code: int, content: bytes, headers: dict[str, str]) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, *, chunk_size: int):
        del chunk_size
        yield self.content

    def close(self) -> None:
        pass


class FakeMediaSession:
    def __init__(
        self,
        payload: bytes,
        calls: list[str | None],
        *,
        supports_ranges: bool,
    ) -> None:
        self.payload = payload
        self.calls = calls
        self.supports_ranges = supports_ranges

    def get(self, url: str, *, headers, **kwargs) -> FakeMediaResponse:
        del url, kwargs
        range_header = headers.get("Range")
        self.calls.append(range_header)
        if not range_header or not self.supports_ranges:
            return FakeMediaResponse(
                200,
                self.payload,
                {
                    "content-type": "video/mp4",
                    "content-length": str(len(self.payload)),
                },
            )
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", range_header)
        assert match is not None
        start, end = (int(value) for value in match.groups())
        return FakeMediaResponse(
            206,
            self.payload[start : end + 1],
            {
                "content-type": "video/mp4",
                "content-length": str(end - start + 1),
                "content-range": f"bytes {start}-{end}/{len(self.payload)}",
            },
        )

    def close(self) -> None:
        pass


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


def test_tiktok_reads_metadata_without_downloading_media() -> None:
    page = b"""
    <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">
    {"scope":{"itemStruct":{"id":"123","desc":"Ho Guom, Van Mieu",
    "author":{"nickname":"Travel VN"},"video":{"duration":12,
    "playAddr":"https://v16-webapp-prime.tiktok.com/video.mp4"}}}}
    </script>
    """

    class PageResponse:
        status_code = 200
        content = page
        text = page.decode()

        def raise_for_status(self):
            pass

    class PageSession:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, **kwargs):
            self.calls += 1
            return PageResponse()

        def close(self):
            pass

    session = PageSession()
    client = TikTokHtmlMediaClient(session_factory=lambda: session)

    metadata = asyncio.run(client.extract(
        "https://www.tiktok.com/@travel/video/123?share=private"
    ))

    assert metadata["description"] == "Ho Guom, Van Mieu"
    assert metadata["duration"] == 12
    assert session.calls == 1


def test_tiktok_html_downloads_four_parallel_ranges(tmp_path) -> None:
    payload = b"0123456789abcdef"
    calls: list[str | None] = []
    client = TikTokHtmlMediaClient(
        max_workers=4,
        session_factory=lambda: FakeMediaSession(
            payload, calls, supports_ranges=True
        ),
    )
    target = tmp_path / "media.mp4"
    primary = FakeMediaSession(payload, calls, supports_ranges=True)

    client._stream_media(
        primary,
        "https://v16-webapp-prime.tiktok.com/video.mp4",
        "https://www.tiktok.com/@creator/video/1",
        target,
    )

    assert target.read_bytes() == payload
    assert calls[0] == "bytes=0-0"
    assert sorted(calls[1:]) == [
        "bytes=0-3",
        "bytes=12-15",
        "bytes=4-7",
        "bytes=8-11",
    ]


def test_tiktok_html_falls_back_when_media_server_ignores_range(tmp_path) -> None:
    payload = b"video served sequentially"
    calls: list[str | None] = []
    client = TikTokHtmlMediaClient(
        max_workers=4,
        session_factory=lambda: FakeMediaSession(
            payload, calls, supports_ranges=False
        ),
    )
    target = tmp_path / "media.mp4"
    primary = FakeMediaSession(payload, calls, supports_ranges=False)

    client._stream_media(
        primary,
        "https://v16-webapp-prime.tiktok.com/video.mp4",
        "https://www.tiktok.com/@creator/video/1",
        target,
    )

    assert target.read_bytes() == payload
    assert calls == ["bytes=0-0", None]
