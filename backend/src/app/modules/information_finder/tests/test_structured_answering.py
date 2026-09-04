from datetime import datetime, timedelta, timezone

import pytest

from app.modules.information_finder.answering import validate_and_render_answer
from app.modules.information_finder.entity_linking import (
    EntityResolver,
    ResolvedEntity,
    materialize_entity_spans,
)
from app.modules.information_finder.contract import (
    FactItem,
    FactListBlock,
    GeneratedAnswer,
    RetrievedSource,
    VerseBlock,
)
from app.modules.information_finder.errors import AnswerProviderInvalidOutput


NOW = datetime.now(timezone.utc)


def source(identifier: str = "source-1") -> RetrievedSource:
    return RetrievedSource(
        source_id=identifier,
        snapshot_id=f"snapshot-{identifier}",
        title="Hồ Hoàn Kiếm",
        url="https://example.test/ho-guom",
        content="Hồ Hoàn Kiếm ở Hà Nội.",
        last_fetched_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )


def test_structured_blocks_render_to_compatibility_text_and_preserve_order():
    generated = GeneratedAnswer(
        blocks=[
            FactListBlock(
                title="Thông tin nổi bật",
                items=[
                    FactItem(
                        label="Xếp hạng",
                        text="Di tích quốc gia đặc biệt năm 2013.",
                        highlights=["năm 2013"],
                        source_ids=["source-1"],
                    )
                ],
            ),
            VerseBlock(
                title="Nghiên Bút Non Sông",
                author="Đình Dương",
                lines=["Dòng một", "Dòng hai"],
                source_ids=["source-1"],
            ),
        ]
    )

    answer, blocks, cited_sources = validate_and_render_answer(generated, [source()])

    assert [block.type for block in blocks] == ["factList", "verse"]
    assert [block.bubble_id for block in blocks] == ["bubble-1", "bubble-2"]
    assert "Xếp hạng" in answer
    assert "Dòng một\nDòng hai" in answer
    assert [item.source_id for item in cited_sources] == ["source-1"]


def test_structured_block_rejects_unknown_source_id():
    generated = GeneratedAnswer(
        blocks=[
            FactListBlock(
                items=[
                    FactItem(
                        label="Xếp hạng",
                        text="Di tích quốc gia đặc biệt.",
                        source_ids=["missing"],
                    )
                ]
            )
        ]
    )

    with pytest.raises(AnswerProviderInvalidOutput):
        validate_and_render_answer(generated, [source()])


class Resolver(EntityResolver):
    async def resolve(self, name: str) -> ResolvedEntity | None:
        if name.casefold() == "hồ hoàn kiếm":
            return ResolvedEntity(name="Hồ Hoàn Kiếm", entity_id="place-1")
        return None


def test_entity_spans_are_materialized_only_for_resolved_entities():
    generated = GeneratedAnswer(
        entity_names=["Hồ Hoàn Kiếm", "Địa danh chưa có node"],
        blocks=[
            FactListBlock(
                items=[
                    FactItem(
                        label="Địa điểm",
                        text="Hồ Hoàn Kiếm là địa danh chưa có node.",
                        source_ids=["source-1"],
                    )
                ]
            )
        ],
    )

    blocks = __import__("asyncio").run(
        materialize_entity_spans(
            generated.blocks,
            entity_names=generated.entity_names,
            entity_candidates=generated.entity_candidates,
            resolver=Resolver(),
        )
    )

    spans = blocks[0].items[0].inline_spans
    assert any(span.type == "entity" and span.entity_id == "place-1" for span in spans)
    assert any(span.type == "text" and "chưa có node" in span.text for span in spans)
