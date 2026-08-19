import asyncio

from app.modules.explorer.adapters.place_consolidation import GeminiPlaceConsolidator
from app.modules.explorer.contract import ExplorerPlace, PlaceSource


class FailingClient:
    async def generate(self, *args, **kwargs) -> str:
        raise AssertionError("exact duplicates must not call Gemini")


def _place(evidence: str) -> ExplorerPlace:
    return ExplorerPlace(
        name="Cầu Rồng",
        sourcePlaces=[PlaceSource(
            origin="url",
            evidenceType="caption",
            sourceUrl="https://example.com",
            evidence=evidence,
        )],
    )


def test_exact_duplicates_skip_gemini_consolidation() -> None:
    consolidator = GeminiPlaceConsolidator(
        FailingClient(),  # type: ignore[arg-type]
        asyncio.Semaphore(1),
        max_output_tokens=4000,
        provider="gemini",
    )

    result = asyncio.run(consolidator.consolidate(
        [_place("mention one"), _place("mention two")],
        "Đà Nẵng",
    ))

    assert len(result) == 1
    assert len(result[0].source_places) == 2
