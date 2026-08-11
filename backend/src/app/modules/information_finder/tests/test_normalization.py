from app.modules.information_finder.normalization import (
    normalize_answer_text,
    select_relevant_excerpt,
)


NOISY_SOURCE = """
Turn your device in landscape mode. Tiếng Việt English 中文 (中国) 한국어 Русский
Đăng nhập Đăng ký Chọn điểm đến Nha Trang VinWonders Nha Trang Phú Quốc Hà Nội
Bước tới nội dung Wikipedia Bách khoa toàn thư mở Tìm kiếm Nội dung 1 Tên gọi
2 Địa lý 3 Lịch sử 9 Văn hóa [1]
Những điều thú vị về Hà Nội khiến bạn thêm yêu mảnh đất nghìn năm văn hiến của
dân tộc Việt Nam. Hà Nội có nhiều công trình văn hóa và khu phố cổ đặc sắc.
"""


def test_normalize_answer_text_removes_scraper_markers_and_collapses_whitespace():
    assert normalize_answer_text("  Fact [1]  from\n  source. ") == "Fact from source."


def test_relevant_excerpt_skips_navigation_prefix():
    excerpt = select_relevant_excerpt(
        NOISY_SOURCE,
        "Những điều thú vị về Hà Nội",
        title="Những điều thú vị về Hà Nội",
        max_chars=220,
    )

    assert "Những điều thú vị về Hà Nội" in excerpt
    assert "Đăng nhập" not in excerpt
    assert "Bước tới nội dung" not in excerpt
