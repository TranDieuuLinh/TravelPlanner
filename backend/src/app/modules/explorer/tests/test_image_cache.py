import asyncio

from app.modules.explorer.adapters.image_cache import InMemoryImageOcrCache
from app.modules.explorer.adapters.image_source import GeminiImageSourceExtractor
from app.modules.explorer.contract import ExplorerImageInput


class CountingAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze_image(self, data_base64: str, mime_type: str) -> str:
        self.calls += 1
        return "Hồ Gươm"


def _image() -> ExplorerImageInput:
    return ExplorerImageInput(
        fileName="hanoi.png",
        mimeType="image/png",
        dataBase64="YWJj",
    )


def test_image_ocr_reuses_hash_cache() -> None:
    analyzer = CountingAnalyzer()
    extractor = GeminiImageSourceExtractor(
        analyzer,  # type: ignore[arg-type]
        cache=InMemoryImageOcrCache(),
    )

    async def invoke_twice() -> None:
        await extractor.extract(_image(), source_index=0, raw_prompt=None)
        await extractor.extract(_image(), source_index=1, raw_prompt=None)

    asyncio.run(invoke_twice())

    assert analyzer.calls == 1


def test_force_refresh_bypasses_image_ocr_cache() -> None:
    analyzer = CountingAnalyzer()
    extractor = GeminiImageSourceExtractor(
        analyzer,  # type: ignore[arg-type]
        cache=InMemoryImageOcrCache(),
    )

    async def invoke_twice() -> None:
        await extractor.extract(_image(), source_index=0, raw_prompt=None)
        await extractor.extract(
            _image(), source_index=1, raw_prompt=None, force_refresh=True
        )

    asyncio.run(invoke_twice())

    assert analyzer.calls == 2


def test_image_ocr_cache_evicts_least_recent_entry() -> None:
    cache = InMemoryImageOcrCache(max_entries=2)

    async def fill() -> tuple[str | None, str | None]:
        await cache.save("first", "one")
        await cache.save("second", "two")
        await cache.get("first")
        await cache.save("third", "three")
        return await cache.get("first"), await cache.get("second")

    first, second = asyncio.run(fill())

    assert first == "one"
    assert second is None
