import asyncio
from datetime import datetime, timedelta, timezone

from app.modules.information_finder.adapters.development import (
    ExtractiveAnswerGenerator,
)
from app.modules.information_finder.contract import RetrievedSource


NOW = datetime.now(timezone.utc)


def source(identifier: str, content: str) -> RetrievedSource:
    return RetrievedSource(
        source_id=identifier,
        snapshot_id=f"snapshot-{identifier}",
        title="Du lịch Vũng Tàu",
        url=f"https://example.test/{identifier}",
        content=content,
        last_fetched_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )


def test_extractive_answer_is_bounded_and_uses_markdown_bullets():
    generator = ExtractiveAnswerGenerator()
    sources = [
        source(str(index), f"Vũng Tàu có điểm tham quan số {index} " * 100)
        for index in range(1, 6)
    ]

    generated = asyncio.run(generator.generate("Vũng Tàu có gì?", sources))

    assert len(generated.claims) == 3
    assert generated.claims[0].text.startswith("- ")
    assert generated.claims[1].text.startswith("- ")
    assert len(generated.claims[0].text.rsplit("- ", 1)[-1]) > 280
    assert all(len(claim.text.rsplit("- ", 1)[-1]) > 280 for claim in generated.claims)


def test_extractive_answer_skips_noisy_source_and_keeps_useful_source():
    generator = ExtractiveAnswerGenerator()
    generated = asyncio.run(
        generator.generate(
            "Vũng Tàu",
            [
                source("noise", "Discover flight with Traveloka. @Shutterstock."),
                source("useful", "Vũng Tàu có các bãi biển phù hợp để dạo bộ."),
            ],
        )
    )

    assert len(generated.claims) == 1
    assert "Vũng Tàu có các bãi biển" in generated.claims[0].text
    assert generated.claims[0].source_ids == ["useful"]


def test_extractive_answer_handles_sources_containing_only_noise():
    generated = asyncio.run(
        ExtractiveAnswerGenerator().generate(
            "Vũng Tàu",
            [source("noise", "Discover flight with Traveloka. @Shutterstock.")],
        )
    )

    assert generated.claims[0].text.startswith("Thông tin hiện có chưa đủ rõ")
    assert generated.claims[0].source_ids == ["noise"]
