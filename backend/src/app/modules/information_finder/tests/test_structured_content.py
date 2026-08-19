from datetime import datetime, timedelta, timezone
import asyncio

from app.modules.information_finder.adapters.development import ExtractiveAnswerGenerator
from app.modules.information_finder.contract import (
    FactItem,
    FactListBlock,
    RetrievedSource,
)
from app.modules.information_finder.structured_content import (
    clean_source_sentences,
    normalize_answer_blocks,
)


NOW = datetime.now(timezone.utc)


def source(content: str) -> RetrievedSource:
    return RetrievedSource(
        source_id="source-1",
        snapshot_id="snapshot-1",
        title="Hồ Hoàn Kiếm",
        url="https://example.test/ho-guom",
        content=content,
        last_fetched_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )


def test_clean_source_sentences_removes_navigation_footer_and_company_copy():
    text = (
        "Di tích được xếp hạng năm 2013. Previous Next Liên kết website. "
        "Công ty ABC Tuyển dụng Văn phòng."
    )

    sentences = clean_source_sentences(text, "xếp hạng", "Hồ Hoàn Kiếm")

    assert sentences == ["Di tích được xếp hạng năm 2013."]


def test_clean_source_sentences_removes_unavailable_url_notice():
    text = (
        "Thông tin về việc truy cập nội dung từ URL được cung cấp hiện không "
        "khả dụng do hạn chế kỹ thuật. Hà Nội có nhiều di tích lịch sử."
    )

    assert clean_source_sentences(text, "Hà Nội", "Hà Nội") == [
        "Hà Nội có nhiều di tích lịch sử."
    ]


def test_clean_source_sentences_drops_navigation_and_source_title_snippets():
    text = (
        "Toàn Cảnh Núi Bà Đen - Tây Ninh 2025 | Hướng Dẫn Chi Tiết. "
        "Bách khoa toàn thư mở. Bỏ qua nội dung."
    )

    assert clean_source_sentences(
        text,
        "giới thiệu Núi Bà Đen",
        "Toàn Cảnh Núi Bà Đen - Tây Ninh 2025 | Hướng Dẫn Chi Tiết",
    ) == []


def test_clean_source_sentences_cuts_at_word_boundary_and_keeps_relevant_fact():
    text = "Hồ Hoàn Kiếm có cảnh quan đẹp và là điểm dạo bộ nổi tiếng ở Hà Nội."

    sentences = clean_source_sentences(
        text,
        "Hồ Hoàn Kiếm",
        "Hồ Hoàn Kiếm",
        max_chars=48,
    )

    assert sentences == ["Hồ Hoàn Kiếm có cảnh quan đẹp và là điểm dạo bộ"]


def test_extractive_fallback_returns_short_fact_blocks_not_raw_snippet():
    generated = asyncio.run(
        ExtractiveAnswerGenerator().generate(
            "xếp hạng",
            [
                source(
                    "Di tích được xếp hạng năm 2013. "
                    "Previous Next Liên kết website. "
                    "Công ty ABC Tuyển dụng Văn phòng."
                )
            ],
        )
    )

    assert len(generated.blocks) <= 5
    assert generated.blocks[0].type == "factList"
    assert "Previous" not in generated.model_dump_json()
    assert len(generated.blocks[0].items[0].text.split()) <= 25


def test_normalize_answer_blocks_drops_boilerplate_items_before_rendering():
    blocks = normalize_answer_blocks(
        [
            FactListBlock(
                items=[
                    FactItem(
                        label="Điều hướng",
                        text="Previous Next Liên kết website.",
                        source_ids=["source-1"],
                    ),
                    FactItem(
                        label="Xếp hạng",
                        text="Di tích quốc gia đặc biệt năm 2013.",
                        source_ids=["source-1"],
                    ),
                ]
            )
        ]
    )

    assert len(blocks) == 1
    assert [item.label for item in blocks[0].items] == ["Xếp hạng"]
